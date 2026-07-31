# Centinela — Sistema de Detección de Fraude en Azure

Sistema de detección de fraude sobre **Microsoft Azure**: ingesta de transacciones (semana 1) y un motor de scoring serverless desacoplado por eventos que evalúa cada transacción contra su historial y abre casos cuando corresponde (semana 2). Tres componentes independientes (`api/`, `scoring/`, `cases/`) comunicados por eventos, sin acoplamiento directo entre ellos.

**🌐 URL de Producción:** `https://app-trial-dev-cus-003.azurewebsites.net`

---

## 🛠️ Tech Stack

| Capa | Tecnología |
|---|---|
| **API de Ingesta** | Python 3.11 + FastAPI + Pydantic v2 |
| **Motor de Scoring** | Azure Functions v2 (Consumption/Y1) — trigger Event Grid |
| **Almacén de Casos** | Azure Functions v2 (Consumption/Y1) — trigger Service Bus |
| **IaC** | Azure Bicep + Bash (`az CLI`) |
| **Cómputo** | Azure App Service Plan B1 (Linux) + Azure Functions |
| **Redes** | Azure VNet, NSG, VNet Integration, Service Endpoints |
| **Datos** | Azure Blob Storage · Cosmos DB SQL API · Azure SQL Serverless |
| **Mensajería** | Azure Event Grid (topic custom) + Azure Service Bus (Basic) |
| **Identidad** | Microsoft Entra ID — Managed Identity sin claves en código |
| **Pruebas** | Pytest (32 + 23 + 13 tests), SQLAlchemy contra SQLite en memoria |

---

## 🌐 API — Referencia de Endpoints

Base URL producción: `https://app-trial-dev-cus-003.azurewebsites.net`

Documentación interactiva: [`/docs`](https://app-trial-dev-cus-003.azurewebsites.net/docs) (Swagger UI generado por FastAPI)

---

### `POST /transactions` — Ingestar transacción

Recibe una transacción, la valida y la persiste. Publica el evento `transaction.received` hacia Event Grid para que el motor de scoring lo procese de forma asíncrona.

**Rate limit:** 60 peticiones / 60 segundos por IP de origen (ventana deslizante en memoria). Responde `429` con cabecera `Retry-After` cuando se supera.

**Request body:**

```json
{
  "transaction_id": "d2ae9603-15e1-45b2-88f5-4da64398afa6",
  "account_id": "acc-12345",
  "amount_minor_units": 15000,
  "currency": "USD",
  "client_timestamp": "2026-07-31T10:00:00Z",
  "location": {
    "latitude": 40.7128,
    "longitude": -74.0060
  },
  "merchant": {
    "merchant_id": "merch-99",
    "category": "5411"
  }
}
```

**Campos del contrato:**

| Campo | Tipo | Restricciones |
|---|---|---|
| `transaction_id` | `string` | UUID v4 — generado por el cliente, actúa como clave de idempotencia |
| `account_id` | `string` | 1–128 caracteres |
| `amount_minor_units` | `integer` | `> 0`, `≤ 10_000_000` (centavos o unidad menor) |
| `currency` | `string` | Código ISO 4217 de 3 letras mayúsculas (ej. `USD`) |
| `client_timestamp` | `datetime` | Con zona horaria; no puede ser futuro (tolerancia: 60 s) |
| `location.latitude` | `float` | `-90` a `90` |
| `location.longitude` | `float` | `-180` a `180` |
| `merchant.merchant_id` | `string` | 1–64 caracteres |
| `merchant.category` | `string` | 1–64 caracteres |

> **Nota:** El modelo usa `extra="forbid"` — cualquier campo adicional no declarado en el contrato provoca un `400`.

**Respuestas:**

| Código | Cuándo | Body |
|---|---|---|
| `201 Created` | Transacción aceptada y persistida por primera vez | `{"transaction_id": "...", "status": "accepted", "received_at": "..."}` |
| `200 OK` | Transacción duplicada (mismo `transaction_id` ya existe) | `{"transaction_id": "...", "status": "already_accepted"}` |
| `400 Bad Request` | Payload inválido: campo faltante, tipo incorrecto, valor fuera de rango, campo extra | `{"error": "payload_invalido", "detail": [...]}` |
| `429 Too Many Requests` | Rate limit excedido | `{"detail": "Límite de peticiones excedido..."}` + `Retry-After` |
| `500 Internal Server Error` | Error inesperado en el servidor | `{"error": "error_interno"}` |

**Ejemplo real (probado en producción 2026-07-31):**

```bash
curl -X POST https://app-trial-dev-cus-003.azurewebsites.net/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "d2ae9603-15e1-45b2-88f5-4da64398afa6",
    "account_id": "acc-12345",
    "amount_minor_units": 15000,
    "currency": "USD",
    "client_timestamp": "2026-07-31T10:00:00Z",
    "location": {"latitude": 40.7128, "longitude": -74.0060},
    "merchant": {"merchant_id": "merch-99", "category": "5411"}
  }'
# → 201 {"transaction_id":"d2ae9603-...","status":"accepted","received_at":"2026-07-31T11:43:25.691429+00:00"}
```

---

### `GET /transactions/{transaction_id}` — Consultar transacción

Recupera una transacción por su `transaction_id`, junto con la marca de tiempo autoritativa asignada por el servidor.

**Respuestas:**

| Código | Cuándo | Body |
|---|---|---|
| `200 OK` | Transacción encontrada | `{"transaction": {...}, "server_received_at": "..."}` |
| `404 Not Found` | ID no existe en el sistema | `{"error": "transaccion_no_encontrada"}` |

**Ejemplo real (probado en producción 2026-07-31):**

```bash
curl https://app-trial-dev-cus-003.azurewebsites.net/transactions/d2ae9603-15e1-45b2-88f5-4da64398afa6
# → 200 {"transaction":{"transaction_id":"d2ae9603-...","account_id":"acc-12345","amount_minor_units":15000,...},"server_received_at":"2026-07-31T11:43:25.691429+00:00"}
```

---

### `POST /documents` — Cargar documento de identidad

Carga un archivo de verificación de identidad al contenedor `identity-documents` de Azure Blob Storage. Requiere `CENTINELA_STORAGE_BACKEND=blob`.

**Validaciones aplicadas:**
- Tipo de archivo por **magic bytes** (no por extensión): acepta PDF, JPEG, PNG.
- Tamaño máximo: `CENTINELA_MAX_DOCUMENT_SIZE_BYTES` (default 10 MB).
- El nombre del blob lo genera el sistema (`{uuid}/{timestamp}.{ext}`) — nunca se usa el nombre original del archivo del usuario.
- Autenticación: `DefaultAzureCredential` (Managed Identity).

**Request:** `multipart/form-data` con campo `file`.

**Respuestas:**

| Código | Cuándo | Body |
|---|---|---|
| `201 Created` | Documento cargado correctamente | `{"status": "accepted", "document_id": "...", "blob_name": "...", "content_type": "...", "size_bytes": ...}` |
| `400 Bad Request` | Tipo de archivo no permitido | `{"error": "tipo_archivo_no_permitido", "detail": "..."}` |
| `400 Bad Request` | Archivo demasiado grande | `{"error": "archivo_demasiado_grande", "detail": "..."}` |
| `503 Service Unavailable` | Backend de almacenamiento no configurado como `blob` | `{"error": "almacenamiento_no_disponible", "detail": "..."}` |

**Ejemplo:**

```bash
curl -X POST https://app-trial-dev-cus-003.azurewebsites.net/documents \
  -F "file=@/ruta/al/documento.pdf"
```

---

### `GET /documents/access-url` — Obtener URL temporal (SAS) de un documento

Genera una URL de lectura temporal y delegada (SAS) sobre un documento específico del contenedor `identity-documents`. Permite que un analista de fraude consulte el documento sin acceso permanente al contenedor.

**Query params:**

| Parámetro | Tipo | Descripción |
|---|---|---|
| `blob_name` | `string` | Valor de `blob_name` devuelto por `POST /documents` (formato `{uuid}/{timestamp}.{ext}`) |

**Respuestas:**

| Código | Cuándo | Body |
|---|---|---|
| `200 OK` | URL generada | `{"url": "https://...", "expires_at": "..."}` — válida 30 minutos, solo lectura |
| `404 Not Found` | El blob no existe en el contenedor | `{"error": "documento_no_encontrado"}` |
| `503 Service Unavailable` | Backend no configurado como `blob` | `{"error": "almacenamiento_no_disponible"}` |

**Ejemplo:**

```bash
curl "https://app-trial-dev-cus-003.azurewebsites.net/documents/access-url?blob_name=abc123/20260731T104500.pdf"
```

---

## 🏗️ Infraestructura Desplegada

Grupo de recursos: `rg-trial-dev-cus-003` — Región: **Central US (`centralus`)**

| Recurso | SKU / Tipo | Nombre | Propósito |
|---|---|---|---|
| **App Service Plan** | Basic (B1) | `plan-trial-dev-cus-003` | Cómputo de la API |
| **Web App (API)** | Linux Python 3.11 | `app-trial-dev-cus-003` | API HTTP de ingesta (FastAPI) |
| **Storage Account** | Standard_LRS | `sttrialdevcus003...` | Blob `transacciones`, `identity-documents`, queues |
| **Cosmos DB (SQL API)** | Free Tier | `cosmos-trial-dev-cus-003` | Historial de transacciones — partición `/account_id`, TTL 30 días |
| **Azure SQL Database** | Serverless GP, Free Offer | `sql-trial-dev-cus-003` / `centinela-casos` | Almacén de casos |
| **Event Grid Topic** | Custom Topic | `evt-trial-dev-cus-003` | Evento `transaction.received` |
| **Service Bus** | Basic | `sb-trial-dev-cus-003` / `casos-marcados` | Cola de casos marcados |
| **Function App (scoring)** | Consumption (Y1) | `func-scoring-trial-dev-cus-003` | Motor de scoring — trigger Event Grid |
| **Function App (cases)** | Consumption (Y1) | `func-cases-trial-dev-cus-003` | Creación de casos — trigger Service Bus |
| **Virtual Network** | `/16` (10.20.0.0/16) | `vnet-trial-dev-cus-003` | Aislamiento de red |
| **Presupuesto** | Consumption Budget | `budget-trial-dev-cus-003` | Alertas en $70, $112, 100% proyectado |

### Topología de red

```
VNet 10.20.0.0/16
 ├── snet-app     (10.20.1.0/24) → Web App (VNet Integration) + Cosmos DB + Event Grid
 ├── snet-st      (10.20.2.0/24) → Storage Account (Service Endpoint: Microsoft.Storage)
 ├── snet-db      (10.20.3.0/24) → Reservada (ADR-019)
 ├── snet-scoring (10.20.4.0/24) → Function Apps + Cosmos DB + SQL + Service Bus
 └── snet-mgt     (10.20.5.0/24) → Gestión / Administración
```

**Política de red:** Denegar por defecto en todos los datastores. El acceso desde internet está rechazado incluso con AAD válido si el origen no está en la VNet permitida.

---

## ⚙️ Variables de Configuración

Todas las variables usan el prefijo `CENTINELA_` (API) o `CENTINELA_SCORING_` (motor de scoring).

### API (`api/`)

| Variable | Default | Descripción |
|---|---|---|
| `CENTINELA_STORAGE_BACKEND` | `memory` | `memory` / `blob` / `dual` |
| `CENTINELA_BLOB_ACCOUNT_URL` | — | URL de la cuenta de Storage (requerida si backend=blob o dual) |
| `CENTINELA_BLOB_CONTAINER_RAW_TRANSACTIONS` | `transacciones` | Contenedor de transacciones |
| `CENTINELA_IDENTITY_BLOB_CONTAINER` | `identity-documents` | Contenedor de documentos de identidad |
| `CENTINELA_MAX_DOCUMENT_SIZE_BYTES` | `10485760` (10 MB) | Tamaño máximo de documento |
| `CENTINELA_EVENT_PUBLISHER_BACKEND` | `noop` | `noop` / `eventgrid` |
| `CENTINELA_EVENT_GRID_TOPIC_ENDPOINT` | — | Endpoint del topic de Event Grid |
| `CENTINELA_COSMOS_ACCOUNT_URL` | — | URL de Cosmos DB (requerida si backend=dual) |
| `CENTINELA_COSMOS_DATABASE_NAME` | `centinela` | Base de datos en Cosmos |
| `CENTINELA_COSMOS_CONTAINER_TRANSACTIONS` | `transactions` | Contenedor de transacciones en Cosmos |
| `CENTINELA_MAX_AMOUNT_MINOR_UNITS` | `10000000` | Monto máximo en unidad menor |
| `CENTINELA_CLOCK_SKEW_TOLERANCE_SECONDS` | `60` | Tolerancia de reloj para `client_timestamp` |
| `CENTINELA_RATE_LIMIT_WINDOW_SECONDS` | `60` | Ventana del rate limiter |
| `CENTINELA_RATE_LIMIT_MAX_REQUESTS` | `60` | Máximo de peticiones por ventana por IP |

### Motor de Scoring (`scoring/`)

| Variable | Default | Descripción |
|---|---|---|
| `CENTINELA_SCORING_COSMOS_ACCOUNT_URL` | — | URL de Cosmos DB (obligatorio) |
| `CENTINELA_SCORING_SERVICEBUS_NAMESPACE_FQDN` | — | FQDN del namespace de Service Bus (obligatorio) |
| `CENTINELA_SCORING_SCORE_THRESHOLD` | `100` | Umbral de apertura de caso (modificable sin redespliegue) |
| `CENTINELA_SCORING_VELOCITY_WINDOW_SECONDS` | `300` | Ventana para regla de velocidad |
| `CENTINELA_SCORING_VELOCITY_MAX_COUNT` | `5` | Máximo de transacciones en ventana |
| `CENTINELA_SCORING_VELOCITY_POINTS` | `30` | Puntos por regla de velocidad |
| `CENTINELA_SCORING_AMOUNT_STDDEV_MULTIPLIER` | `3.0` | Multiplicador de desviación estándar para monto atípico |
| `CENTINELA_SCORING_AMOUNT_POINTS` | `40` | Puntos por monto atípico |
| `CENTINELA_SCORING_GEO_MAX_SPEED_KMH` | `900.0` | Velocidad máxima plausible (km/h) para geo-imposible |
| `CENTINELA_SCORING_GEO_POINTS` | `50` | Puntos por geo-imposible |
| `CENTINELA_SCORING_RISKY_CATEGORIES_CSV` | `gambling,crypto_exchange,money_transfer` | Categorías de riesgo |
| `CENTINELA_SCORING_RISKY_MERCHANT_POINTS` | `25` | Puntos por comercio de riesgo |

---

## 🧠 Motor de Scoring — Las 4 Reglas

El motor evalúa cada transacción contra el historial de la cuenta en Cosmos DB. El score es la suma de puntos de las reglas activadas. Si supera el `score_threshold` (default: 100), se publica un mensaje a la cola `casos-marcados` de Service Bus.

| Regla | ID | Puntos | Se activa cuando... |
|---|---|---|---|
| **Velocidad** | `velocidad` | 30 | ≥ 5 transacciones de la misma cuenta en los últimos 5 min |
| **Monto atípico** | `monto_atipico` | 40 | Monto > media + 3σ del historial (requiere ≥ 3 registros históricos) |
| **Geo-imposible** | `geo_imposible` | 50 | Velocidad de desplazamiento implícita > 900 km/h entre dos transacciones |
| **Comercio de riesgo** | `comercio_riesgo` | 25 | Categoría o `merchant_id` en lista de riesgo configurada |

Cada regla activada persiste los valores concretos que la activaron (no solo el ID), por ejemplo: distancia en km, velocidad implícita, desviación estándar, conteo de transacciones en ventana.

---

## 📁 Estructura del Repositorio

```
├── api/                         # API FastAPI de ingesta
│   ├── app/
│   │   ├── api/routes.py        # Endpoints HTTP
│   │   ├── core/config.py       # Variables de entorno (CENTINELA_*)
│   │   ├── core/rate_limiter.py # Limitador de tasa por IP (ventana deslizante)
│   │   ├── models/transaction.py# Contrato Pydantic v2 (extra="forbid")
│   │   ├── services/ingestion.py# Lógica: validar → persistir → publicar evento
│   │   ├── storage/             # Adaptadores: Memory, Blob, Cosmos, Dual
│   │   └── messaging/           # Publishers: NoOp, Event Grid
│   └── tests/                   # 32 tests (Pytest)
├── scoring/                     # Motor de scoring — Azure Function
│   ├── rules.py                 # 4 reglas de detección (lógica pura, sin I/O)
│   ├── orchestration.py         # historial → reglas → persistencia → publicación
│   ├── cosmos_repository.py     # Adaptador Cosmos DB
│   ├── servicebus_publisher.py  # Adaptador Service Bus
│   ├── config.py                # Variables de entorno (CENTINELA_SCORING_*)
│   ├── function_app.py          # Binding Azure Functions (trigger Event Grid)
│   └── tests/                   # 23 tests
├── cases/                       # Almacén de casos — Azure Function
│   ├── models.py                # SQLAlchemy: Caso, Estado, Asignación, Resolución
│   ├── repository.py            # Idempotente por transaction_id
│   ├── db.py                    # SQLite (tests) / Azure SQL AAD-only (producción)
│   ├── schema.sql               # DDL T-SQL para Azure SQL
│   ├── function_app.py          # Binding Azure Functions (trigger Service Bus)
│   └── tests/                   # 13 tests
├── docs/                        # Documentación técnica y entregables formales
├── infra/
│   ├── bicep/                   # Módulos: network, storage, cosmos, sql, eventing,
│   │                            # functions, app, rbac, budget
│   ├── deploy-all.sh            # Aprovisionamiento completo automatizado
│   └── shutdown.sh              # Apagado y control de costo diario
└── test_prod.py                 # Script de prueba contra la API en producción
```

---

## 🚀 Despliegue

### Aprovisionamiento completo

```bash
chmod +x infra/deploy-all.sh infra/shutdown.sh
az login
./infra/deploy-all.sh
```

### Ejecución local (sin Azure)

```bash
# API de ingesta
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
python -m pytest -v   # 32 tests

# Motor de scoring
cd scoring
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -v   # 23 tests

# Almacén de casos
cd cases
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -v   # 13 tests
```

### Apagado (control de costos)

```bash
./infra/shutdown.sh
# Opciones:
# 1. Detener solo la Web App
# 2. Escalar plan a F1 (gratuito) + detener Web App
# 3. Eliminar el grupo de recursos completo
```

---

## ✅ Pruebas en Producción (2026-07-31)

Ejecutadas con `test_prod.py` contra `https://app-trial-dev-cus-003.azurewebsites.net`:

| Prueba | Resultado |
|---|---|
| `POST /transactions` — payload válido | ✅ `201 Created` |
| `GET /transactions/{id}` — recuperar la transacción creada | ✅ `200 OK` con datos completos + `server_received_at` |
| `POST /transactions` — monto negativo (`amount_minor_units: -5000`) | ✅ `400 Bad Request` con detalle del campo inválido |
| Idempotencia — reenvío del mismo `transaction_id` | ✅ `200 OK` con `status: already_accepted` |
| Rate limit — 60 req/min configurado, no alcanzado en las 15 peticiones de prueba | ✅ Comportamiento esperado |

---

## 📚 Documentación Técnica

| Documento | Descripción |
|---|---|
| [contrato-transaccion.md](docs/contrato-transaccion.md) | Contrato formal del payload de transacción |
| [codigos-estado.md](docs/codigos-estado.md) | Tabla de códigos HTTP y su semántica |
| [idempotencia.md](docs/idempotencia.md) | Estrategia de idempotencia por `transaction_id` |
| [limite-tasa-api.md](docs/limite-tasa-api.md) | Rate limiting: diseño, limitaciones y umbrales |
| [decisiones-arquitectura.md](docs/decisiones-arquitectura.md) | Registro de decisiones (ADR) de ambas semanas |
| [diagrama-red.md](docs/diagrama-red.md) | Topología de red y subredes |
| [tabla-reglas-trafico.md](docs/tabla-reglas-trafico.md) | Reglas NSG por subred |
| [prueba-aislamiento-red.md](docs/prueba-aislamiento-red.md) | Evidencia de aislamiento de red (HTTP 403) |
| [autenticacion-autorizacion.md](docs/autenticacion-autorizacion.md) | Managed Identity y RBAC |
| [matriz-roles-permisos.md](docs/matriz-roles-permisos.md) | Roles RBAC por componente |
| [justificacion-particionamiento-cosmos.md](docs/justificacion-particionamiento-cosmos.md) | Diseño de particionamiento Cosmos DB |
| [umbral-scoring.md](docs/umbral-scoring.md) | Justificación del umbral de scoring (100 pts) |
| [mensajeria-semana2.md](docs/mensajeria-semana2.md) | Event Grid vs Service Bus — decisión arquitectónica |
| [prueba-desacoplamiento.md](docs/prueba-desacoplamiento.md) | Runbook de prueba de desacoplamiento |
| [estrategia-respaldo-sql.md](docs/estrategia-respaldo-sql.md) | Backup de Azure SQL |
| [reporte-credito-consumido.md](docs/reporte-credito-consumido.md) | Consumo de crédito Azure |
