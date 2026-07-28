# Contrato de la transacción

Entregable 15. Define la estructura de datos que atraviesa todo el sistema
(Azure-Semana1.md, sección 2.8). Implementado en
`api/app/models/transaction.py`. Su modificación implica intervenir la API,
el motor de scoring, la mensajería y los almacenes simultáneamente — por eso
se congela esta semana y cualquier cambio posterior debe registrarse en
`docs/decisiones-arquitectura.md`.

## 1. Campos

| Campo | Tipo | Obligatorio | Formato / rango | Responde a |
|---|---|---|---|---|
| `transaction_id` | string | Sí | UUID v4 | ¿Cómo se identifica de forma única? |
| `account_id` | string | Sí | 1–128 caracteres | ¿De qué cuenta proviene? |
| `amount_minor_units` | entero | Sí | > 0, ≤ máximo configurado (`CENTINELA_MAX_AMOUNT_MINOR_UNITS`) | ¿Cuál es el monto? |
| `currency` | string | Sí | ISO 4217, 3 letras mayúsculas (p. ej. `USD`) | ¿Cuál es el monto? |
| `client_timestamp` | string (ISO 8601, con zona horaria) | Sí | No puede ser futuro (tolerancia de reloj configurable, por defecto 60 s) | ¿En qué instante exacto ocurrió? (con matiz, ver §2) |
| `location.latitude` | float | Sí | -90 a 90 | ¿Desde qué ubicación se originó? |
| `location.longitude` | float | Sí | -180 a 180 | ¿Desde qué ubicación se originó? |
| `merchant.merchant_id` | string | Sí | 1–64 caracteres | ¿Hacia qué comercio o categoría se dirige? |
| `merchant.category` | string | Sí | 1–64 caracteres | ¿Hacia qué comercio o categoría se dirige? |

Campo generado por el servidor, **no** enviado por el cliente:

| Campo | Tipo | Origen |
|---|---|---|
| `server_received_at` | string (ISO 8601 UTC) | Asignado por la API al momento de persistir. Es el valor autoritativo para las reglas de velocidad y geo-imposible. |

Cualquier campo fuera de esta lista se rechaza (ver §2.5).

## 2. Las cuatro decisiones

### 2.1 Marca de tiempo

**Decisión: dos campos, uno declarado y uno autoritativo.**

- `client_timestamp`: lo declara el sistema de origen (canal, terminal, app).
  Es informativo — sirve para trazabilidad y para detectar discrepancias
  sospechosas entre lo que el cliente dice y lo que el servidor observa —
  pero **no se usa para evaluar las reglas de detección**.
- `server_received_at`: lo asigna la API en el instante de persistir, en
  UTC. Es el valor autoritativo que deben usar la regla de velocidad y la
  regla geo-imposible en la semana 2.

**Justificación:** si se aceptara el `client_timestamp` como fuente de
verdad para la regla de velocidad, un actor malicioso podría manipular su
reloj local para evadirla (enviar transacciones con timestamps espaciados
artificialmente mientras en realidad llegan en ráfaga). Separar "lo que el
cliente dice" de "lo que el servidor observa" cierra ese vector.

Zona horaria: **UTC** en ambos campos, formato ISO 8601 con offset explícito
(`...Z` o `+00:00`). El validador rechaza timestamps sin zona horaria: un
timestamp naive es ambiguo entre servidores/regiones y ese ambiguedad es
exactamente lo que las reglas de velocidad y geo-imposible no pueden tolerar.

### 2.2 Monto

**Decisión: entero en la unidad monetaria menor (`amount_minor_units`) + código de moneda ISO 4217 separado.**

Ejemplo: USD 15.00 se representa como `amount_minor_units: 1500, currency: "USD"`.

**Justificación — por qué no coma flotante:** los tipos de punto flotante
binario (`float`/`double`) no pueden representar exactamente la mayoría de
valores decimales (0.1 + 0.2 ≠ 0.3 en binario). En un sistema financiero eso
produce errores de redondeo acumulativos y comparaciones inexactas
(`monto == umbral` puede fallar por un residuo de 1e-16). Representar el
monto como entero en la unidad menor elimina el problema por completo: toda
la aritmética relevante (sumas para detectar velocidad de gasto,
comparaciones contra umbrales) es aritmética entera exacta.

**Por qué no `decimal` serializado como string:** se evaluó, pero exige que
cada consumidor (motor de scoring, almacenes, reportes) parsee e interprete
el decimal correctamente, y complica los índices y agregaciones en los
almacenes de la semana 2. El entero en unidad menor es el estándar de facto
en APIs de pagos (Stripe, entre otros) precisamente por esto.

**Nota:** no todas las monedas tienen 2 decimales (p. ej. JPY tiene 0, KWD
tiene 3). La conversión "unidad mayor → unidad menor" depende de la moneda;
esa lógica de presentación vive en los clientes/consumidores, no en el
contrato.

### 2.3 Ubicación

**Decisión: par de coordenadas decimales WGS84 (`latitude`, `longitude`).**

**Justificación:** la regla geo-imposible (semana 2) necesita calcular la
distancia entre dos ubicaciones sucesivas y contrastarla contra el tiempo
transcurrido, para inferir si un mismo titular pudo desplazarse
físicamente entre ambos puntos. Un par lat/lon en grados decimales permite
aplicar directamente la fórmula de Haversine (o Vincenty, si se requiere
mayor precisión) sin transformación adicional. Alternativas descartadas:
- Dirección de texto libre: no permite calcular distancia sin geocodificar
  primero, y la geocodificación introduce una dependencia externa y
  latencia en el camino crítico de ingesta.
- Solo país/ciudad: insuficiente resolución para distinguir "misma ciudad,
  dos comercios" de "geo-imposible real".

### 2.4 Identificador

**Decisión: `transaction_id` es un UUID v4 generado por el sistema de origen (el cliente/canal que emite la transacción), no por el servidor.**

**Justificación:** la API debe poder confirmar la aceptación de forma
idempotente ante reintentos (ver `docs/idempotencia.md`). Si el
identificador lo generara el servidor, cada reintento de un cliente que no
recibió el acuse (p. ej. por timeout de red) produciría un
`transaction_id` distinto y, por lo tanto, una transacción duplicada
irreconciliable. Generándolo el origen, el mismo reintento llega con el
mismo `transaction_id` y la API puede reconocerlo como ya procesado.

**Comportamiento ante duplicados:** ver `docs/idempotencia.md`. En resumen:
la API verifica existencia antes de persistir; si el id ya existe, responde
`200` con `status: already_accepted` sin volver a persistir ni volver a
publicar el evento hacia el motor de scoring.

**Riesgo aceptado:** esto asume que el sistema de origen es confiable para
generar UUIDs v4 sin colisión (probabilidad de colisión de UUID v4:
despreciable) y que no reutiliza intencionalmente un id para una
transacción distinta. Los canales de origen están dentro del perímetro de
confianza de Centinela (autenticados vía el rol Servicio); un canal externo
no confiable no está contemplado en el alcance de la semana 1.

### 2.5 Campos no contemplados en el contrato

**Decisión: se rechazan (HTTP 400).** El esquema es estricto
(`extra="forbid"` en el modelo Pydantic): cualquier campo fuera de los
listados en §1 causa el rechazo de todo el payload.

**Justificación:** en un sistema financiero, aceptar y descartar
silenciosamente campos desconocidos oculta errores de integración del lado
del cliente (p. ej. un campo mal nombrado que el emisor cree que se está
guardando) y abre la puerta a que un cliente empiece a depender
informalmente de un comportamiento no contractual. Rechazar explícitamente
fuerza a que cualquier cambio de contrato pase por el proceso documentado en
`docs/decisiones-arquitectura.md`.
