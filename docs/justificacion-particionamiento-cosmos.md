# Justificación del diseño de particionamiento — Cosmos DB

Entregable 2 de semana 2. Almacén de transacciones NoSQL
(`Azure-Semana2.md`, sección 2.1) — `infra/bicep/modules/cosmos.bicep`.

## 1. Clave de partición: `/account_id`

**Consulta que optimiza:** "obtener las transacciones recientes de una
cuenta determinada" — la consulta dominante del sistema, ejecutada por el
motor de scoring en cada transacción procesada
(`scoring/cosmos_repository.py::query_recent_history`). Con partición por
`account_id`, esa consulta es de **partición única**
(`partition_key=account_id` explícito en la llamada al SDK) — Cosmos la
resuelve dentro de una sola partición física, sin recorrer las demás.

**Consulta que sacrifica:** cualquier consulta que agrupe por algo
distinto de la cuenta — por ejemplo, "todas las transacciones hacia un
comercio dado" (útil para análisis retrospectivo de un comercio de
riesgo) requeriría una consulta **cross-partición** (fan-out a todas las
particiones), cara en RU y sin garantía de rendimiento predecible al
crecer el número de cuentas.

**Lookup por `transaction_id` — deliberadamente NO resuelto por esta
partición.** `GET /transactions/{id}` (semana 1) sigue resolviéndose
contra Blob Storage, que sí indexa por id de forma nativa (nombre del
blob = `transaction_id`). Si se intentara resolver ese mismo lookup
contra Cosmos sin conocer el `account_id` de antemano, también sería
cross-partición. Mantener Blob como autoridad de ese lookup (ver
`docs/decisiones-arquitectura.md`, ADR sobre persistencia dual) evita ese
costo por completo — es la razón concreta por la que la partición de
Cosmos puede optimizarse exclusivamente para el patrón de consulta del
motor de scoring, sin comprometer el lookup por id.

**Alternativa descartada: `/transaction_id`.** Optimizaría el lookup por
id (que ya no hace falta, resuelto por Blob) pero convertiría la consulta
dominante — historial por cuenta — en cross-partición. Se descarta porque
optimiza la consulta equivocada: la sección 2.1 es explícita en que el
perfil de carga tiene "una consulta dominante" y es la de historial por
cuenta, no el lookup por id.

**Alternativa descartada: `/merchant_id` o `/category`.** No sirve a
ninguna de las dos consultas reales del sistema (historial por cuenta,
lookup por id); se descarta sin mayor análisis.

La clave de partición no admite modificación posterior sin migración
completa de los datos (sección 2.1) — por eso esta decisión se toma y
justifica ahora, antes de la primera escritura, no se deja como "ajustar
después".

## 2. Nivel de consistencia: Session

**Elegido:** Session — lecturas monotónicas dentro de la misma sesión
(mismo cliente/token de sesión), latencia y costo de RU menores que
Strong o Bounded Staleness, mayor que Eventual.

**Por qué no Strong:** requeriría replicar sincrónicamente antes de
confirmar cada escritura, con mayor latencia y costo — no se necesita: el
motor de scoring no requiere ver instantáneamente cada escritura de
*otro* proceso, solo un historial "razonablemente reciente" de la cuenta.

**Por qué no Eventual:** sin ninguna garantía de orden, una misma
Function podría en teoría leer versiones desordenadas entre invocaciones
sucesivas sobre la misma cuenta — Session evita ese caso sin pagar el
costo de Strong.

**Matiz importante, documentado explícitamente (no asumido):** Session
garantiza lecturas monotónicas dentro de la MISMA sesión/token — la API
(que escribe) y el motor de scoring (que lee el historial) son **procesos
distintos, con clientes Cosmos distintos**. No hay garantía automática de
que el motor de scoring vea, en su consulta de historial, la transacción
que la API acaba de escribir hace instantes. Por eso el diseño **no
depende de esa garantía**: el evento publicado por la API
(`api/app/services/ingestion.py`) lleva la transacción completa, no solo
el id — el motor de scoring nunca necesita releer Cosmos para *su propia*
transacción, solo para el historial de transacciones *anteriores* de la
cuenta, donde una leve staleness entre procesos es aceptable y no afecta
la corrección de las reglas (a lo sumo, una transacción publicada
simultáneamente por la misma cuenta podría no verse todavía — un caso de
borde razonable para un sistema de detección, no una falla de
integridad).

## 3. Política de expiración (TTL): 30 días

`defaultTtl` del contenedor: **2,592,000 segundos (30 días)**.

**Relación con las ventanas de las reglas** (`scoring/rules.py`):

| Regla | Ventana que usa | ¿Cabe en 30 días? |
|---|---|---|
| Velocidad | Minutos (`velocity_window_seconds`, default 300s = 5 min) | Sí, ampliamente |
| Geo-imposible | Solo la transacción anterior inmediata, sin ventana fija | Sí |
| Monto atípico | Línea base histórica — la más larga de las 4 | Determina el TTL |
| Comercio de riesgo | Sin historial, solo la transacción actual | No aplica |

30 días cubre la ventana más exigente (la línea base de "monto atípico",
que necesita suficiente historial para que la media/desviación estándar
sean representativas del comportamiento normal de la cuenta) con margen.
Un TTL más corto degradaría esa línea base; uno más largo no aporta valor
analítico adicional a ninguna de las 4 reglas y solo aumenta el
almacenamiento consumido.

**El TTL de Cosmos no borra el caso.** Si una transacción activó un caso,
el caso vive en el almacén relacional (`cases/`, Azure SQL) de forma
indefinida, con su propia estrategia de respaldo
(`docs/estrategia-respaldo-sql.md`) — expirar el registro operativo de
Cosmos a los 30 días no tiene ningún efecto sobre casos ya abiertos.

## 4. Nivel de servicio gratuito

**Free Tier de Cosmos DB:** 1000 RU/s + 25GB de almacenamiento,
gratuitos, **uno por suscripción**. `infra/bicep/modules/cosmos.bicep`
activa `enableFreeTier: true`.

**Riesgo documentado, no verificable sin `az` real:** si la suscripción
ya tiene otra cuenta Cosmos con el Free Tier activado, esta cuenta no
calificará y se facturará a tarifa estándar desde el primer RU. No hay
forma de confirmar esto desde este entorno de desarrollo — debe
verificarse antes del primer despliegue real:

```bash
az cosmosdb list --query "[].{name:name, freeTier:enableFreeTier}" -o table
```

**Límites del nivel gratuito relevantes para Centinela:** 1000 RU/s
compartidos entre todas las operaciones (consulta de historial +
escritura de score + escritura inicial de la API) — suficiente para el
volumen de prueba de la célula en 21 días, insuficiente si se simula
carga real de producción (fuera de alcance de esta semana).
