# Documento de decisiones de arquitectura

Entregable 25. Acompaña las tres semanas del proyecto Centinela. Se
registra aquí toda decisión de arquitectura no trivial, con su alternativa
descartada y la razón. Formato ADR simplificado: Contexto / Decisión /
Alternativas descartadas / Consecuencias.

Este documento lo inició Persona 4 con las decisiones de su alcance
(contrato, API, idempotencia, nivel de servicio: ADR-001 a 008). Las
personas 1, 2 y 3 completaron las suyas en ADR-009 a 013 (región y costo,
convención de nombres, crédito consumido, identidad, red/almacenamiento/
cola).

---

## ADR-001 — Persistencia de la transacción cruda en Blob Storage (semana 1)

**Contexto:** la sección 2.9 exige persistir la transacción cruda al
recibirla, pero los almacenes relacional y documental no se despliegan
hasta la semana 2 (sección 1, "fuera de alcance"). Se necesita un destino
de persistencia disponible desde el día 1.

**Decisión:** cada transacción se persiste como un blob JSON individual en
un contenedor `raw-transactions`, usando `transaction_id` como nombre de
blob.

**Alternativas descartadas:** persistencia en archivo local del App
Service (no sobrevive reinicios/escalado, y App Service en Linux no
garantiza almacenamiento persistente entre instancias); adelantar el
despliegue de una base de datos a la semana 1 (fuera del alcance
explícito de la semana, sección 1).

**Consecuencias:** en la semana 2, cuando se despliegue el almacén
definitivo, el punto de persistencia (`app/storage/ports.py`) ya está
abstraído detrás de una interfaz — agregar un backend relacional/documental
es una nueva implementación de `TransactionStorage`, seleccionable por
configuración (`app/storage/factory.py`), sin tocar la capa de servicio ni
el endpoint.

## ADR-002 — Identificador de transacción generado por el cliente de origen

Ver justificación completa en `docs/contrato-transaccion.md` §2.4.
Consecuencia directa: la estrategia de idempotencia (`docs/idempotencia.md`)
depende de que el origen no reutilice un `transaction_id` para dos
transacciones distintas.

## ADR-003 — Timestamp dual: `client_timestamp` informativo, `server_received_at` autoritativo

Ver justificación completa en `docs/contrato-transaccion.md` §2.1.

## ADR-004 — Monto como entero en unidad menor + ISO 4217, sin coma flotante

Ver justificación completa en `docs/contrato-transaccion.md` §2.2.

## ADR-005 — Política de campos no contemplados: rechazo estricto

Ver justificación completa en `docs/contrato-transaccion.md` §2.5.

## ADR-006 — Homologación de errores de validación a HTTP 400

**Contexto:** FastAPI devuelve `422` por defecto para errores de Pydantic.

**Decisión:** todo error de incumplimiento del contrato (forma o
semántica) responde `400 Bad Request`.

**Alternativas descartadas:** mantener `422` para errores de forma y `400`
para errores semánticos (dos códigos para la misma categoría de problema —
"tu payload no es válido" — añade una distinción que el cliente de la API
no necesita).

**Consecuencias:** documentado en `docs/codigos-estado.md`. Cualquier
consumidor de la API debe tratar `400` como "corrige el payload y
reintenta", nunca como error transitorio.

## ADR-007 — Nivel de servicio App Service: Basic B1

Ver justificación completa en `docs/nivel-servicio-costo.md`.

## ADR-008 — Punto de inserción de mensajería: tras persistir, antes de responder

**Contexto:** la sección 2.9 exige que el código esté estructurado en capas
de modo que agregar la publicación de eventos en la semana 2 no requiera
reescribir el endpoint.

**Decisión:** `IngestionService.ingest()` invoca un `EventPublisher`
(interfaz) inmediatamente después de persistir y antes de retornar. La
semana 1 usa `NoOpEventPublisher`; la semana 2 activa el publisher real
cambiando `CENTINELA_EVENT_PUBLISHER_BACKEND` por configuración.

**Consecuencias:** el endpoint (`app/api/routes.py`) y la firma de
`IngestionService.ingest()` no cambian en la semana 2.

---

## ADR-009 — Región de despliegue: West Europe sobre East US 2 (Persona 1)

**Contexto:** el default original del script (`main.bicep`) era
`eastus2`. Al primer despliegue, la suscripción de prueba devolvió
`SubscriptionIsOverQuotaForSku` para planes Linux — cuota 0 confirmada vía
`az rest` contra la API de uso real, no asumida.

**Decisión:** `westeurope`, única región que confirmó cuota activa para
B1 Linux con VNet Integration en una prueba empírica sobre 7 regiones
candidatas. Justificación completa, incluyendo el hueco pendiente de
verificar Cosmos DB/SQL para semana 2, en `docs/justificacion-region.md`.

**Alternativas descartadas:** `eastus2` (cuota 0, bloqueo duro), otras 6
regiones probadas en el mismo lote sin confirmar viabilidad para B1 Linux.

**Consecuencias:** `regionShort=weu` se propaga a todos los módulos Bicep
vía el parámetro `regionShort` de `main.bicep`; ningún nombre de recurso
quedó hardcodeado a `eus2`.

## ADR-010 — Convención de nombres: patrón posicional + resolución de unicidad global (Persona 1)

**Contexto:** la sección 2.4 exige una convención que cubra proyecto, tipo
de recurso, ambiente, y resuelva el caso de nombres que deben ser únicos
globalmente (Storage Account, Web App).

**Decisión:** patrón `<tipo>-<prefix>-<env>-<regionShort>-<instance>`,
con `uniqueString(resourceGroup().id)` para la Storage Account (unicidad
automática). Detalle completo, incluyendo la limitación identificada en
la Web App (unicidad resuelta manualmente vía `instance`, no con hash),
en `docs/convencion-nombres.md`.

**Alternativas descartadas:** nombres estáticos por recurso (viola el
criterio de aceptación "ningún nombre de recurso está escrito
directamente en el cuerpo del script").

**Consecuencias:** cualquier colisión de nombre de Web App requiere subir
`instance` manualmente; queda registrado como mejora pendiente, no
aplicada en semana 1.

## ADR-011 — Reporte de crédito: metodología documentada, cifra real pendiente de verificación en vivo (Persona 1)

**Contexto:** entregable 24 exige crédito consumido + proyección a 3
semanas. La proyección de semanas 2 y 3 depende de la selección de
almacén de datos, que `docs/informe-cuotas.md` §5 deja pendiente.

**Decisión:** documentar la metodología, el comando exacto de consulta y
el estimado de referencia (no verificado) en
`docs/reporte-credito-consumido.md`, en lugar de reportar una cifra de
consumo inventada. Se señala explícitamente que el consumo real
probablemente exceda el estimado de "despliegue único" por las
iteraciones de depuración documentadas en `Fixing Bicep Budget Deployment
Errors.md`.

**Alternativas descartadas:** reportar el estimado de costo de
`docs/nivel-servicio-costo.md` como si fuera consumo real verificado —
descartado por ser engañoso.

**Consecuencias:** este entregable queda con una acción pendiente
explícita (§6 de `docs/reporte-credito-consumido.md`): ejecutar la
consulta real contra la suscripción antes de cerrar la semana.

## ADR-012 — Rol Servicio con permisos exclusivos de plano de datos, sin claves de cuenta (Persona 2)

**Contexto:** la sección 2.6 exige que cada permiso del rol Servicio tenga
una operación concreta asociada, separación explícita entre plano de
control y plano de datos, y autenticación exclusivamente por identidad
gestionada.

**Decisión:** Managed Identity `SystemAssigned` en la Web App
(`app.bicep`), con `Storage Blob Data Contributor` (contenedores
`transacciones` e `identity-documents`) y `Storage Queue Data Contributor`
(cola `mensajes`) asignados vía `rbac.bicep` — ambos roles de datos puros
(`actions: []` en su definición), sin ninguna acción de plano de control.
Matriz completa, con la operación que justifica cada permiso, en
`docs/matriz-roles-permisos.md`. El detalle de dónde ocurre la
autenticación (IMDS + Entra ID) y dónde la autorización (plano de datos
de Storage evaluando RBAC) está en `docs/autenticacion-autorizacion.md`.

**Alternativas descartadas:** `Storage Blob Data Owner` (permite
gestionar permisos RBAC, exceso de privilegio para un componente que solo
lee/escribe blobs); claves de cuenta o connection strings (acceso total
sin segmentación por contenedor, requieren rotación manual).

**Consecuencias:** los roles Analista y Auditor de fraude no tienen
usuarios reales en Entra ID en esta suscripción de prueba (individual,
sin directorio de equipo) — las 3 pruebas negativas de la sección 2.6 se
verificaron por análisis de los permisos de cada rol integrado
(`actions: []` en `Storage Blob Data Reader`/`Reader`/`Storage Blob Data
Contributor`), documentado en `docs/pruebas-acceso-negativo.md`, en lugar
de con una ejecución real contra cuentas de usuario. Esto queda
registrado como limitación de esta semana, no como prueba completa contra
usuarios reales.

## ADR-013 — Aislamiento de red por Service Endpoints + `defaultAction: Deny`, cola sin dead-letter nativo (Persona 3)

**Contexto:** la sección 2.7 exige que los almacenes de datos no sean
alcanzables desde internet, con el mecanismo de restricción por subred
gratuito de la plataforma; la sección 2.11 exige política de mensajes
fallidos para la cola de ingesta.

**Decisión — red:** 5 subredes `/24` sobre `10.20.0.0/16` (`snet-app`,
`snet-st` con NSGs de denegar-por-defecto, más `snet-db`/`snet-scoring`/
`snet-mgt` reservadas sin recursos para semana 2/3). Aislamiento de
Storage mediante Service Endpoint (`Microsoft.Storage`) en `snet-app` +
`networkAcls.defaultAction: Deny` en la cuenta — mecanismo gratuito de la
plataforma, sobre Private Endpoints (de pago). Topología y reglas
completas en `docs/diagrama-red.md` (entregable 12) y
`docs/tabla-reglas-trafico.md` (entregable 13); comparación con Private
Endpoints y evidencia de bloqueo real (HTTP 403 + error de regla de red
desde IP externa) en `docs/prueba-aislamiento-red.md`.

**Decisión — cola:** Azure Storage Queues no tiene dead-letter nativo (a
diferencia de Service Bus); la política de mensajes envenenados se
implementa en el consumidor usando `dequeue_count`, con umbral de 5
intentos antes de mover el mensaje a la cola auxiliar `mensajes-poison`
(creada junto a `mensajes` en `storage.bicep`). Los tres escenarios de la
sección 2.11 (fallo antes de confirmar, fallo reiterado, cola creciendo
más rápido de lo que se vacía) están documentados en
`docs/garantias-entrega-cola.md`.

**Decisión — almacenamiento de objetos:** redundancia `Standard_LRS`
(la más económica que cumple preservación de evidencia dentro del
presupuesto de suscripción de prueba) con política de ciclo de vida
(`tierToCool` a 30 días, `tierToArchive` a 90, `delete` a 365) sobre los
contenedores `transacciones` e `identity-documents` (`storage.bicep`).

**Alternativas descartadas:** Private Endpoints para el aislamiento de
red (de pago, fuera de presupuesto de la suscripción gratuita); redundancia
GRS/ZRS para el contenedor de objetos (mayor costo, no justificado para
una fase de prueba de 21 días).

**Consecuencias:** las reglas de tráfico específicas para `snet-db` y
`snet-scoring` quedan sin definir hasta que esos componentes se
seleccionen en semana 2 (fuera de alcance de esta semana, sección 1);
registrado como pendiente explícito en `docs/diagrama-red.md` §4.

## ADR-014 — Acceso de analistas a documentos vía User Delegation SAS (Persona 4)

**Contexto:** `docs/autenticacion-autorizacion.md` y
`docs/matriz-roles-permisos.md` describían el acceso del Analista de
fraude a `identity-documents` como un SAS temporal y delegado, sin
implementación real — la sección 2.10 exige que este mecanismo exista, no
solo que esté descrito ("no se admite exponer el contenedor
públicamente").

**Decisión:** endpoint `GET /documents/access-url` (`api/app/api/routes.py`),
respaldado por `BlobDocumentStorage.generate_read_sas_url`
(`api/app/storage/document_storage.py`). La Web App pide un *user
delegation key* a Entra ID con su propia Managed Identity
(`get_user_delegation_key`, acción `generateUserDelegationKey`, ya
incluida en `Storage Blob Data Contributor` — sin RBAC adicional) y firma
con ese key un SAS de solo lectura acotado a un único blob, válido 30
minutos (`DEFAULT_SAS_EXPIRY_MINUTES`).

**Alternativas descartadas:** SAS de cuenta (`account_key`) — requeriría
generar y custodiar una clave de cuenta, prohibido por 2.6/2.10; rol RBAC
permanente `Storage Blob Data Reader` para el analista sobre todo el
contenedor — viola "no se admite exponer el contenedor públicamente" al
dar acceso a todos los documentos, no solo al del caso en curso.

**Consecuencias:** el endpoint recibe `blob_name` explícito porque la
semana 1 no tiene un almacén documental que asocie casos con documentos
(fuera de alcance, sección 1) — esa asociación es responsabilidad de la
semana 2. Probado con `api/tests/test_documents.py` simulando la
respuesta de `get_user_delegation_key` (no requiere credenciales reales
de Azure para la prueba unitaria); no probado end-to-end contra la
suscripción real.

---

# Semana 2 — Motor de scoring y arquitectura orientada a eventos

Persona 4 implementó también la infraestructura formalmente de Persona 1
(Cosmos DB) y Persona 3 (Event Grid, Service Bus) para que el pipeline
fuera demostrable de punta a punta, con el mismo criterio que en semana 1.

## ADR-015 — Persistencia dual Blob + Cosmos DB, sin reemplazar el store de semana 1

**Contexto:** la sección 2.1 exige un almacén no relacional para
transacciones y scores, con "historial reciente de una cuenta" como
consulta dominante. La API ya persistía la transacción cruda en Blob
Storage (semana 1), autoridad de idempotencia y de `GET /transactions/{id}`.

**Decisión:** no reemplazar Blob — añadir Cosmos DB como store operativo
adicional, vía `DualTransactionStorage`
(`api/app/storage/dual_storage.py`), que implementa el mismo `Protocol
TransactionStorage` de siempre. `exists()`/`get()` siguen delegando 100%
a Blob (autoridad); `save()` escribe a Blob de forma bloqueante y a
Cosmos de forma best-effort (se loguea el error, no se relanza). Detalle
completo del particionamiento/consistencia/TTL de Cosmos en
`docs/justificacion-particionamiento-cosmos.md`.

**Razón de diseño, no solo continuidad:** la partición de Cosmos es
`/account_id`, no `/transaction_id` — resolver el lookup por id contra
Cosmos sería una consulta cross-partición cara en RU. Mantener Blob como
autoridad de ese lookup evita ese costo por completo; es el motivo
concreto (no solo "ya estaba probado") de mantener dos stores con roles
distintos en vez de migrar.

**Alternativas descartadas:** reemplazar Blob por Cosmos como único store
(obligaría a resolver `GET /transactions/{id}` con una consulta cara o a
cambiar la clave de partición, violando el requisito de que la partición
no se puede cambiar sin migración completa); hacer ambas escrituras
bloqueantes (haría que un fallo transitorio de Cosmos rompiera la
ingesta, contradice el objetivo de que Cosmos es aditivo).

**Consecuencias:** una transacción podría faltar en Cosmos si esa
escritura falla — no hay reintento automático esta semana, documentado
explícitamente en el docstring de `DualTransactionStorage`. Probado en
`api/tests/test_dual_storage.py`, incluido el caso de fallo parcial.

## ADR-016 — El evento de transacción lleva el payload completo

**Contexto:** el punto de inserción de semana 1
(`IngestionService.ingest()`) publicaba `{"transaction_id": ...}`
únicamente. El motor de scoring de semana 2 necesita los datos de la
transacción para evaluarla.

**Decisión:** el payload publicado ahora incluye `account_id`,
`amount_minor_units`, `currency`, `server_received_at`, `location` y
`merchant` — la transacción completa, no solo el id.

**Razón:** con consistencia Session en Cosmos DB, la API y la Function de
scoring son procesos con clientes distintos, sin garantía automática de
que la Function vea el registro que la API acaba de escribir. Al viajar
la transacción completa en el evento, la Function nunca depende de
releer Cosmos para SU PROPIA transacción — solo consulta Cosmos para el
historial de transacciones ANTERIORES de la cuenta, donde una leve
staleness sí es aceptable. Ver matiz completo en
`docs/justificacion-particionamiento-cosmos.md` §2.

**Alternativas descartadas:** mantener el payload mínimo y que la
Function relea Cosmos por `transaction_id` — descartado porque introduce
una dependencia de consistencia cross-servicio que Session no garantiza.

**Consecuencias:** el único cambio de lógica real en
`IngestionService.ingest()` para toda la semana 2 — el punto de
inserción, la firma y el resto del servicio no cambian (se cumple la
promesa de ADR-008). Probado en `api/tests/test_ingestion.py::
test_published_event_carries_full_transaction_not_just_id`.

## ADR-017 — Mensajería: Event Grid (distribución) + Service Bus Basic (garantía)

**Contexto:** la sección 2.4 exige dos mecanismos de mensajería con
propósito distinto y la diferencia documentada.

**Decisión:** Event Grid (topic personalizado) para la distribución del
evento de transacción; Service Bus (tier Basic, cola `casos-marcados`,
`maxDeliveryCount=5`, dead-lettering nativo) para la cola de casos
marcados. Comparación completa, incluida la relación con la política
manual de Storage Queue de semana 1, en `docs/mensajeria-semana2.md`.

**Alternativas descartadas:** un único mecanismo (Storage Queue o Service
Bus) para ambos propósitos — no permite documentar una diferencia real
entre "notificar" y "garantizar", que es exactamente lo que pide el
entregable; Service Bus tier Standard/Premium — costo base mensual
innecesario, Basic cubre el caso de uso (cola simple, sin tópicos ni
sesiones).

**Consecuencias:** autenticación AAD en ambos (`EventGrid Data Sender` /
`Azure Service Bus Data Sender-Receiver`), sin claves — igual principio
que el resto del proyecto. GUIDs de rol nuevos no verificados contra
`az role definition list` en este entorno (ver nota en
`infra/bicep/modules/rbac.bicep`).

## ADR-018 — Motor de scoring: separación de lógica pura y umbral configurable

**Contexto:** la sección 2.3 exige 4 reglas, un umbral modificable sin
redespliegue, y registro del detalle concreto de activación (no solo el
id de la regla).

**Decisión:** `scoring/rules.py` (lógica pura, sin imports de Azure) +
`scoring/orchestration.py` (orquesta consulta de historial → evaluación →
persistencia → publicación condicional, con `HistoryRepository`/
`CasePublisher` como `Protocol` inyectados) + `scoring/function_app.py`
(capa delgada de Azure Functions). El umbral y los puntos por regla son
App Settings (`CENTINELA_SCORING_*`), leídos por `scoring/config.py`.
Justificación completa del umbral y de los puntos por regla en
`docs/umbral-scoring.md`.

**Alternativas descartadas:** embeber el umbral en código (viola
literalmente el entregable); una sola función monolítica sin separar
lógica pura de I/O (habría hecho que ninguna prueba de las reglas pudiera
correr sin Azure real, mismo problema que se evitó en semana 1 con
`document_storage.py`).

**Consecuencias:** las 4 reglas y su combinación están cubiertas por 23
tests en `scoring/tests/`, ejecutables sin ninguna credencial de Azure —
la parte de mayor riesgo de bugs (aritmética de cada regla) es también la
más verificada en esta sesión.

## ADR-019 — Almacén de casos: Azure SQL AAD-only, aislado por Service Endpoint sobre `snet-scoring`

**Contexto:** la sección 2.2 exige un almacén relacional con 5 entidades,
aislado de internet, con estrategia de respaldo.

**Decisión:** Azure SQL Database, Serverless General Purpose con Free
Offer, `azureADOnlyAuthentication: true` (sin usuario/contraseña SQL).
Aislamiento por Service Endpoint restringido a `snet-scoring` (no Private
Endpoint sobre `snet-db`) — mismo mecanismo gratuito elegido en semana 1
para Storage, extendido aquí por consistencia y costo (Private Endpoint
son ~$7/mes cada uno; con Cosmos + SQL comerían buena parte del
presupuesto de $40 de la semana). Consecuencia: `snet-db` (reservada en
semana 1) queda sin uso real esta semana — mismo tipo de nota honesta que
ya se documentó para subredes reservadas en `docs/diagrama-red.md` de
semana 1. Modelo relacional (`cases/models.py`, `cases/schema.sql`) y
estrategia de respaldo en `docs/estrategia-respaldo-sql.md`.

**Caveat real, no resuelto por Bicep:** autenticar contra SQL vía AAD
desde Python (`pyodbc`) requiere pasar el token de
`DefaultAzureCredential` vía `SQL_COPT_SS_ACCESS_TOKEN`
(`cases/db.py::create_azure_sql_engine`) y, antes de eso, ejecutar una
sola vez contra la base real:

```sql
CREATE USER [<nombre-managed-identity-cases-function>] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [<nombre-managed-identity-cases-function>];
ALTER ROLE db_datawriter ADD MEMBER [<nombre-managed-identity-cases-function>];
```

Este paso T-SQL no es expresable en Bicep — queda documentado como acción
manual pendiente en `infra/bicep/modules/rbac.bicep` y repetido en
`infra/deploy-all.sh` al final del despliegue.

**Alternativas descartadas:** Private Endpoint sobre `snet-db` (más
costoso, más "correcto" respecto al diseño de red original — se deja
registrado como mejora futura, no aplicada esta semana); SQL
authentication con usuario/contraseña (prohibido por el principio de cero
claves del proyecto).

## ADR-020 — Sin Key Vault propio (decisión explícita, no un olvido)

**Contexto:** la sección 2.6 (Persona 2, fuera del alcance directo de
Persona 4) exige gestión de secretos vía Key Vault.

**Decisión:** el diseño de semana 2 no genera ningún secreto. Cosmos DB
(`disableLocalAuth: true`), Service Bus (`disableLocalAuth: true`), Event
Grid (rol AAD, sin clave del topic) y Azure SQL (`azureADOnlyAuthentication:
true`) se autentican exclusivamente vía identidad gestionada — no hay
connection string con contraseña ni clave compartida en ningún
componente de Persona 4.

**Consecuencia:** no hay nada que Persona 4 necesite guardar en Key
Vault. Si Persona 2 monta un Key Vault de todas formas por completitud
del entregable formal 2.6, es una extensión válida (y probablemente
esperada por el ejercicio) pero no bloqueante para el pipeline de
Persona 4 — se deja registrado para que no se lea como un entregable
omitido por descuido.

## ADR-021 — Limitación de tasa en la aplicación, no en la plataforma

**Contexto:** la sección 2.7 (Persona 2) exige limitar peticiones por
origen en `POST /transactions`, la única que dispara costo en cascada
(persistencia + evento + motor de scoring). Se implementó junto con el
resto de la semana porque era el único entregable con hueco real de
diseño detectado en la revisión de cierre (a diferencia de Key Vault,
donde la ausencia de secretos ya está justificada por ADR-020).

**Decisión:** limitador de ventana deslizante en memoria
(`api/app/core/rate_limiter.py::InMemoryRateLimiter`), por IP de origen
(`X-Forwarded-For` con fallback a `request.client.host`), aplicado como
dependencia de FastAPI solo sobre `POST /transactions`. Valores por
defecto y su justificación completa en `docs/limite-tasa-api.md`.

**Alternativas descartadas:** Azure API Management — descartado
explícitamente por la propia sección 2.7 ("el proyecto no contempla una
capa de gestión de API con nivel de servicio dedicado"); mecanismo de
restricción nativo de App Service — se prefirió la aplicación por poder
responder `429` + `Retry-After` en vez de cortar la conexión, y por ser
testeable sin desplegar nada.

**Consecuencia documentada, no un defecto silencioso:** el conteo es
por-instancia del proceso — exacto con la única instancia B1 actual, se
degradaría (límite efectivo = `max_requests × instancias`) si se
habilita auto-escalado horizontal en semana 3. Ver `docs/limite-tasa-api.md`
§4. Probado con 6 tests (`api/tests/test_rate_limit.py`), incluida la
reactivación del límite tras pasar la ventana usando un reloj inyectable.
