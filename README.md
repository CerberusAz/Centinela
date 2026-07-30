# Centinela — Semana 1 y 2: Ingesta, Motor de Scoring y Mensajería

Sistema de detección de fraude sobre **Microsoft Azure**: ingesta de transacciones (semana 1) y, sobre esa base, un motor de scoring serverless desacoplado por eventos que evalúa cada transacción contra su historial y abre casos cuando corresponde (semana 2). Enfocado en control de costos, seguridad de red, identidad gestionada sin claves, y desacoplamiento arquitectónico real (no solo aparente).

---

## 🛠️ Tech Stack & Tecnologías

- **Lenguaje y Frameworks**: Python 3.11+ / FastAPI (API de ingesta) + Azure Functions v2 (motor de scoring y creación de casos)
- **Infraestructura como Código (IaC)**: Azure Bicep (Módulos parametrizados e idempotentes) + Shell Scripts (`az CLI`)
- **Cómputo & Plataforma**: Azure App Service (Plan B1 Linux) + Azure Functions (Consumption/Y1, Linux, Python 3.11)
- **Redes & Seguridad**: Azure Virtual Network (VNet), Network Security Groups (NSGs), VNet Regional Integration, Service Endpoints (`Microsoft.Storage`, `Microsoft.AzureCosmosDB`, `Microsoft.Sql`, `Microsoft.ServiceBus`)
- **Almacenamiento y Datos**: Azure Blob Storage, Azure Storage Queues (semana 1) · Azure Cosmos DB — SQL API (semana 2, historial/scores) · Azure SQL Database — Serverless (semana 2, almacén de casos, SQLAlchemy)
- **Mensajería (semana 2)**: Azure Event Grid (distribución del evento de transacción) + Azure Service Bus, tier Basic (cola de casos marcados, dead-lettering nativo)
- **Gestión de Identidad & RBAC**: Microsoft Entra ID, System-Assigned Managed Identity en los 3 componentes de cómputo, Azure Role Assignments (RBAC de plano de datos) — sin claves de cuenta ni connection strings en ningún componente
- **Pruebas y Calidad**: Pytest, Pydantic v2 (validación estricta de contrato), SQLAlchemy (modelo relacional testeado contra SQLite en memoria)

---

## 🏗️ Recursos Desplegados & Arquitectura de Red

La infraestructura se aprovisiona automáticamente en el grupo de recursos `rg-trial-dev-weu-003` en la región **West Europe (`westeurope`)**.

### 1. Mapa de Recursos Aprovisionados

| Recurso | Tipo / SKU | Nombre | Propósito |
|---|---|---|---|
| **Resource Group** | RG | `rg-trial-dev-weu-003` | Contenedor lógico de la solución |
| **App Service Plan** | Basic (B1) | `plan-trial-dev-weu-003` | Cómputo exclusivo con soporte VNet Integration |
| **Web App (API)** | Linux Python 3.11 | `app-trial-dev-weu-003` | API HTTP de ingesta (FastAPI) |
| **Storage Account** | Standard_LRS | `sttrialdevweu003...` | Persistencia cruda, documentos y mensajería |
| **Blob Container** | Private (No anonymous) | `transacciones` | Almacenamiento de transacciones JSON crudas |
| **Blob Container** | Private (No anonymous) | `identity-documents` | Almacenamiento de evidencias/documentos de identidad |
| **Storage Queue** | Standard Queue | `mensajes`, `mensajes-poison` | Colas de semana 1 — **sin uso real desde semana 2**, ver nota en `docs/garantias-entrega-cola.md` |
| **Virtual Network** | `/16` (10.20.0.0/16) | `vnet-trial-dev-weu-003` | Red privada de aislamiento |
| **Presupuesto** | Consumption Budget | `budget-trial-dev-weu-003` | Alertas de consumo ($70, $112, 100% proyectado) |
| **Cosmos DB (SQL API)** | Free Tier | `cosmos-trial-dev-weu-003` | Historial de transacciones y scores, partición `/account_id`, TTL 30 días |
| **Azure SQL Database** | Serverless GP, Free Offer | `sql-trial-dev-weu-003` / `centinela-casos` | Almacén de casos (Caso, Estado, Asignación, Resolución, Auditoría) |
| **Event Grid Topic** | Custom Topic | `evt-trial-dev-weu-003` | Distribución del evento `transaction.received` |
| **Service Bus Namespace** | Basic | `sb-trial-dev-weu-003` / cola `casos-marcados` | Cola de casos marcados, garantía at-least-once |
| **Function App** | Consumption (Y1), Linux, Python 3.11 | `func-scoring-trial-dev-weu-003` | Motor de scoring — trigger Event Grid |
| **Function App** | Consumption (Y1), Linux, Python 3.11 | `func-cases-trial-dev-weu-003` | Creación de casos — trigger Service Bus |
| **Storage Account** | Standard_LRS | `stfntrialdevweu003...` | Runtime de las dos Function Apps (`AzureWebJobsStorage`, cuenta separada de la de negocio) |

---

### 2. Topology de Subredes y Reglas NSG (Acceso de Red)

La red `10.20.0.0/16` está segmentada en 5 subredes preparadas para el escalado de las semanas 2 y 3, bajo la política estricta de **Denegar por Defecto**:

```
VNet 10.20.0.0/16
 ├── snet-app     (10.20.1.0/24) -> Web App (VNet Integration) + Cosmos DB + Event Grid (outbound)
 ├── snet-st      (10.20.2.0/24) -> Storage Account (Service Endpoint: Microsoft.Storage)
 ├── snet-db      (10.20.3.0/24) -> Reservada, sin uso real esta semana (ver docs/decisiones-arquitectura.md, ADR-019)
 ├── snet-scoring (10.20.4.0/24) -> Ambas Function Apps (VNet Integration) + Cosmos DB + SQL + Service Bus (outbound)
 └── snet-mgt     (10.20.5.0/24) -> Subred de Gestión / Administración
```

#### Reglas de Tráfico (Network Security Groups)

- **`nsg-app` (Subred de Aplicaciones - 10.20.1.0/24)**
  - `Inbound`: `AllowManagementToAppService` (TCP 443 desde `10.20.5.0/24`). `DenyAllVnetInbound` (Priority 4095).
  - `Outbound`: `AllowAppServiceToStorageOutbound` (443 hacia `10.20.2.0/24`), `AllowAppServiceToCosmosDbOutbound` (443 hacia tag `AzureCosmosDB`), `AllowAppServiceToEventGridOutbound` (443 hacia tag `EventGrid`).

- **`nsg-st` (Subred de Almacenamiento - 10.20.2.0/24)**
  - `Inbound`: `AllowAppServiceToBlob` y `AllowAppServiceToQueue` (TCP 443 desde `10.20.1.0/24`). `DenyInternetToStorage` (Priority 4000: Bloquea todo tráfico desde `Internet`). `DenyAllVnetInbound` (Priority 4095).
  - `Outbound`: `DenyStorageToInternet` (Priority 4000: Bloquea salidas hacia `Internet`).

- **`nsg-scoring` (Subred de Scoring - 10.20.4.0/24, nueva en semana 2)**
  - `Outbound`: `AllowScoringToCosmosDbOutbound` (443 hacia tag `AzureCosmosDB`), `AllowScoringToSqlOutbound` (1433 hacia tag `Sql`), `AllowScoringToServiceBusOutbound` (443 hacia tag `ServiceBus`). `DenyAllVnetInbound` (Priority 4095).

- **Aislamiento de datos** (mismo mecanismo en las 4 stores — gratuito, sin Private Endpoints):
  - Storage: `networkAcls.defaultAction: Deny`, solo `snet-app`.
  - Cosmos DB: `isVirtualNetworkFilterEnabled: true`, `snet-app` + `snet-scoring`, más `disableLocalAuth: true` (sin claves).
  - Azure SQL: `virtualNetworkRules` sobre `snet-scoring`, más `azureADOnlyAuthentication: true`.
  - Service Bus: `networkRuleSets.defaultAction: Deny`, solo `snet-scoring`, más `disableLocalAuth: true`.
  - El acceso a datos desde internet es **rechazado** incluso para usuarios autenticados por AAD si el origen de red no está en la lista permitida (evidencia para Storage en `docs/prueba-aislamiento-red.md`; evidencia equivalente para Cosmos/SQL/Service Bus queda pendiente de ejecución real, ver tabla de validación de cierre de semana 2 más abajo).
  - Event Grid es la única excepción: no soporta restricción por Service Endpoint — su seguridad depende exclusivamente de AAD (rol "EventGrid Data Sender"), documentado explícitamente en `infra/bicep/modules/eventing.bicep`.

---

## 💰 Análisis de Costos & Presupuesto

- **Límite de Consumo Semana 1**: < $20 USD. **Límite acumulado Semana 2**: < $40 USD (`Azure-Semana2.md`, criterios de aceptación).
- **Presupuesto Mensual Configurado**: $140 USD.
- Cifras reales de ambas semanas: `docs/reporte-credito-consumido.md` — metodología lista, consumo real sin verificar (requiere `az login`, no disponible en este entorno de desarrollo).

### Estructura de Costos Estimada — Semana 1 (21 Días del Proyecto)

| Componente | Nivel / SKU | Estimado (21 Días) | Estrategia de Ahorro |
|---|---|---|---|
| **App Service Plan** | Basic (B1) | ~$9.50 - $13.50 USD | Se apaga al final de la jornada con `./infra/shutdown.sh` |
| **Storage Account** | Standard_LRS | ~$0.10 - $0.50 USD | Nivel LRS (más económico) + Lifecycle policy activa |
| **VNet / Subredes / NSGs** | Estándar | $0.00 USD | Gratuitos en Azure |
| **Service Endpoints** | Red | $0.00 USD | Sin cargo adicional (alternativa costo $0 vs Private Endpoints) |
| **Total Estimado Semana 1** | — | **~$10.00 - $14.00 USD** | **Dentro del límite de $20 USD** |

### Estructura de Costos Estimada — Componentes Nuevos de Semana 2

| Componente | Nivel / SKU | Estimado | Estrategia de Ahorro |
|---|---|---|---|
| **Cosmos DB** | Free Tier (1000 RU/s + 25GB) | $0.00 USD | Free Tier — riesgo: solo 1 por suscripción, no verificado (`docs/justificacion-particionamiento-cosmos.md` §4) |
| **Azure SQL Database** | Serverless GP, Free Offer, auto-pause | ~$0.00 USD (dentro del Free Offer) | Fallback si no aplica: Basic ~$5/mes, sigue bajo el límite |
| **Event Grid** | Pay-per-operation | Centavos, volumen de prueba | Sin costo base mensual |
| **Service Bus** | Basic | Centavos, volumen de prueba | Tier más económico, sin tópicos/sesiones que no se usan |
| **2 Function Apps** | Consumption (Y1) | ~$0.00 USD (dentro de la capa gratuita mensual) | Serverless — sin costo si no hay invocaciones |
| **Storage Account (Functions runtime)** | Standard_LRS | ~$0.10 USD | Cuenta separada, mínimo tráfico |
| **Total estimado, componentes nuevos** | — | **Order de magnitud: unos pocos USD** | No verificado contra facturación real — ver riesgo de elegibilidad de Free Tier/Offer |

---

## 📁 Estructura del Repositorio

```text
├── Azure-Semana1.md / Azure-Semana2.md   # Especificaciones oficiales de requerimientos
├── README.md                    # Documentación principal del sistema
├── api/                         # API FastAPI de ingesta (semana 1, extendida en semana 2)
│   ├── app/
│   │   ├── api/routes.py        # Endpoints HTTP (POST /transactions, GET /transactions/{id}, POST /documents, GET /documents/access-url)
│   │   ├── core/config.py       # Configuración externalizada (variables CENTINELA_)
│   │   ├── models/              # Modelos Pydantic (contrato de transacción y validaciones)
│   │   ├── services/ingestion.py# Orquestación de ingesta, idempotencia, evento enriquecido (semana 2)
│   │   ├── storage/             # Adaptadores: Blob, Memory, Cosmos (semana 2), Dual (semana 2)
│   │   └── messaging/           # Publishers: NoOp (semana 1), Event Grid (semana 2)
│   ├── tests/                   # Suite de pruebas automatizadas (Pytest)
│   └── requirements.txt         # Dependencias Python
├── scoring/                     # Motor de scoring (semana 2) — Azure Function independiente
│   ├── rules.py                 # Las 4 reglas de detección, lógica pura sin Azure
│   ├── orchestration.py         # Orquesta consulta de historial -> reglas -> persistencia -> publicación
│   ├── cosmos_repository.py     # Adaptador real contra Cosmos DB
│   ├── servicebus_publisher.py  # Adaptador real contra Service Bus (cola de casos)
│   ├── config.py                # Configuración externalizada (CENTINELA_SCORING_*, incluye el umbral)
│   ├── function_app.py          # Binding de Azure Functions (trigger de Event Grid)
│   └── tests/                   # Pruebas sin Azure real (reglas + orquestación con dobles)
├── cases/                       # Almacén de casos (semana 2) — Azure Function independiente
│   ├── models.py                # SQLAlchemy: Caso, Estado, Asignación, Resolución, Auditoría
│   ├── schema.sql                # DDL T-SQL equivalente para Azure SQL real
│   ├── repository.py            # Capa de repositorio (idempotente por transaction_id)
│   ├── db.py                     # Conexión SQLite (tests) y Azure SQL AAD-only (producción)
│   ├── function_app.py          # Binding de Azure Functions (trigger de Service Bus)
│   └── tests/                   # Pruebas contra SQLite en memoria, sin Azure real
├── docs/                        # Entregables formales de arquitectura (semana 1 y 2)
│   ├── decisiones-arquitectura.md        # Entregable 25 (s1) / 14 (s2): registro de decisiones (ADR)
│   ├── justificacion-particionamiento-cosmos.md  # Entregable 2 (s2)
│   ├── umbral-scoring.md                 # Justificación del umbral (s2)
│   ├── mensajeria-semana2.md             # Entregable 8 (s2): Event Grid vs Service Bus
│   ├── prueba-desacoplamiento.md         # Entregable 10 (s2): runbook
│   ├── estrategia-respaldo-sql.md        # Entregable 4 (s2)
│   └── (resto de entregables de semana 1, ver índice más abajo)
└── infra/                       # Infraestructura como Código (Bicep + Bash)
    ├── bicep/                   # main + módulos: network, storage, cosmos, sql, eventing, functions, app, rbac, budget
    ├── deploy-all.sh            # Script maestro de aprovisionamiento (infra + código de los 3 componentes)
    └── shutdown.sh              # Script maestro de apagado y control de costos
```

---

## 🚀 Despliegue y Operación

### 1. Despliegue Automatizado en Azure

Para desplegar la infraestructura completa y el código de la API en una suscripción limpia:

```bash
# Otorgar permisos de ejecución
chmod +x infra/deploy-all.sh infra/shutdown.sh

# Iniciar sesión en Azure
az login

# Ejecutar aprovisionamiento automatizado e idempotente
./infra/deploy-all.sh
```

### 2. Ejecución Local para Desarrollo y Pruebas

Los tres componentes (`api/`, `scoring/`, `cases/`) son independientes, cada uno con su propio `requirements.txt` y venv. Ninguno de los tres requiere credenciales de Azure para correr su suite de pruebas — es el mismo principio de diseño aplicado en los tres: separar lógica pura testeable de los adaptadores reales de I/O.

**API de ingesta** (en memoria, sin Azure):

```bash
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000   # servidor local
python -m pytest -v                          # 32 tests
```

**Motor de scoring** (las 4 reglas + orquestación, sin Azure):

```bash
cd scoring
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -v                          # 23 tests
```

**Almacén de casos** (modelo relacional completo contra SQLite en memoria):

```bash
cd cases
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -v                          # 13 tests
```

Para correr `scoring/` o `cases/` como Azure Function real localmente (Azure Functions Core Tools), copiar `local.settings.json.example` a `local.settings.json` y completar los valores de Cosmos DB / Service Bus / Azure SQL reales — no cubierto por este README porque no se pudo probar en este entorno de desarrollo (sin `az`/red hacia Azure).

### 3. Apagado de Recursos (Control de Costo Diario)

Al finalizar la jornada laboral, ejecutar el script de apagado interactivo:

```bash
./infra/shutdown.sh
```
*Opciones disponibles:*
1. Detener únicamente la Web App.
2. Escalar App Service Plan a F1 (Gratuito) y detener Web App.
3. Eliminar por completo el Grupo de Recursos.

---

## ✅ Validación de cierre (sección 4 de `Azure-Semana1.md`)

Secuencia de 10 pasos que la especificación exige ejecutar y registrar
antes de dar la semana por concluida. Estado real al día de hoy — un
paso marcado ⚠️ o ❌ es trabajo pendiente, no un error de documentación:

| # | Paso | Estado | Evidencia / lo que falta |
|---|---|---|---|
| 1 | Eliminar el grupo de recursos completo | ❌ No ejecutado en esta validación | Requiere `az login` real; usar `infra/teardown-all.sh` o la opción 3 de `infra/shutdown.sh` |
| 2 | Ejecutar el script de aprovisionamiento sobre la suscripción vacía | ⚠️ Parcial | `infra/deploy-all.sh` se ejecutó varias veces durante desarrollo (`Fixing Bicep Budget Deployment Errors.md`), pero no hay una corrida limpia registrada inmediatamente después del paso 1 |
| 3 | Completar la configuración siguiendo exclusivamente el README | ⚠️ No verificado por un tercero | Nadie ajeno al equipo probó levantar el sistema solo con este README |
| 4 | Enviar una transacción válida y verificar su persistencia | ⚠️ Parcial | Cubierto por `api/tests/test_ingestion.py` en local (memoria); sin evidencia contra la instancia desplegada en Azure |
| 5 | Enviar una transacción inválida y verificar el rechazo | ⚠️ Parcial | Mismo caso que el punto 4 — cubierto localmente, no contra Azure real |
| 6 | Cargar un documento y verificar su llegada al contenedor | ❌ Sin evidencia | Endpoint `POST /documents` existe (`api/app/api/routes.py`) pero no hay prueba registrada, ni automatizada ni manual |
| 7 | Escribir y leer un mensaje de la cola | ❌ Sin evidencia | Cola `mensajes` (y `mensajes-poison`) creadas en `storage.bicep`, sin prueba de escritura/lectura real registrada |
| 8 | Intentar alcanzar el almacenamiento desde internet y verificar el bloqueo | ✅ Hecho | `docs/prueba-aislamiento-red.md` — HTTP 403 y error de regla de red, evidencia con timestamp |
| 9 | Consultar y registrar el crédito consumido | ❌ Pendiente | `docs/reporte-credito-consumido.md` — metodología y comando listos, cifra real sin consultar |
| 10 | Ejecutar el script de apagado | ⚠️ Script listo, sin registro de ejecución diaria | `infra/shutdown.sh` — no hay bitácora de que se haya corrido al cierre de cada jornada |

**Lectura de esta tabla:** según la sección 4 de `Azure-Semana1.md`,
"cualquier paso que requiera conocimiento no documentado indica trabajo
pendiente". Los pasos 1, 6, 7 y 9 no se pueden completar desde este
repositorio — necesitan una sesión con `az login` contra la suscripción
real.

---

## ✅ Validación de cierre (sección 4 de `Azure-Semana2.md`)

| # | Criterio | Estado | Evidencia / lo que falta |
|---|---|---|---|
| 1 | La API responde antes de que el scoring finalice (marcas de tiempo) | ❌ No ejecutado | Runbook listo en `docs/prueba-desacoplamiento.md` §Paso 1; requiere despliegue real + Application Insights |
| 2 | Con el consumidor de casos detenido, la API sigue respondiendo | ❌ No ejecutado | Runbook §Paso 2 |
| 3 | Al restablecer el consumidor, los casos se procesan sin pérdida | ❌ No ejecutado | Runbook §Paso 3 — la idempotencia que lo garantiza (`cases/repository.py`) sí está probada localmente |
| 4 | El motor de scoring consulta una única cuenta (métrica de consumo RU) | ⚠️ Parcial | Consulta de partición única implementada (`scoring/cosmos_repository.py`); logging de RU es best-effort, no verificado contra el SDK real |
| 5 | Política de expiración elimina registros fuera de ventana | ❌ No verificado | `defaultTtl` configurado en `cosmos.bicep`; comportamiento real no observado |
| 6 | Almacén de casos no alcanzable desde internet | ❌ No verificado | Mecanismo configurado (`sql.bicep`, Service Endpoint); sin evidencia tipo `docs/prueba-aislamiento-red.md` |
| 7 | Ambos almacenes dentro del nivel gratuito | ⚠️ Riesgo documentado | Elegibilidad de Free Tier/Free Offer no verificable sin `az` real (uno por suscripción) |
| 8 | Las 4 reglas activan correctamente (velocidad, monto, geo, comercio) | ✅ Hecho | 23 tests en `scoring/tests/test_rules.py`, todos los casos límite cubiertos |
| 9 | Umbral se modifica sin redespliegue | ✅ Hecho (diseño) | App Setting `CENTINELA_SCORING_SCORE_THRESHOLD`; probado a nivel unitario, no contra una Function real desplegada |
| 10 | Cada regla persiste los valores concretos, no solo el id | ✅ Hecho | `RuleActivation.details` en `scoring/rules.py`, verificado en tests |
| 11 | Sin credenciales en código/repo/historial | ✅ Hecho | AAD-only / Managed Identity en los 3 componentes; sin Key Vault propio porque no hay secretos que guardar (ADR-020) |
| 12 | Componentes acceden al gestor de secretos vía identidad gestionada | N/A para Persona 4 | No hay secretos que gestionar en este diseño (ver ADR-020); Key Vault es entregable de Persona 2 |
| 13 | Límite de tasa responde con código correcto | ✅ Hecho | `api/app/core/rate_limiter.py`, aplicado a `POST /transactions`. 6 tests en `api/tests/test_rate_limit.py`; comportamiento bajo carga real y con múltiples instancias no verificado (`docs/limite-tasa-api.md` §4) |
| 14 | Crédito acumulado semana 2 < $40 USD | ❌ Pendiente | Metodología en `docs/reporte-credito-consumido.md`; cifra real sin consultar |

**Lo que sí se puede afirmar sin Azure real:** las 4 reglas de detección
y el almacén de casos (23 + 13 = 36 tests) están correctos a nivel
lógico. Lo que queda pendiente es exclusivamente la verificación contra
recursos reales desplegados — mismo patrón que semana 1.

---

## 📚 Documentación Técnica de Referencia

**Semana 1**

- [Contrato de Transacción](docs/contrato-transaccion.md)
- [Informe de Cuotas](docs/informe-cuotas.md)
- [Justificación de Región](docs/justificacion-region.md)
- [Convención de Nombres](docs/convencion-nombres.md)
- [Diagrama de Red](docs/diagrama-red.md)
- [Tabla de Reglas de Tráfico](docs/tabla-reglas-trafico.md)
- [Prueba de Aislamiento de Red](docs/prueba-aislamiento-red.md)
- [Garantías de Entrega en Cola](docs/garantias-entrega-cola.md) *(ver nota de corrección de semana 2 al inicio)*
- [Matriz de Roles y Permisos RBAC](docs/matriz-roles-permisos.md)
- [Bitácora de Pruebas Negativas](docs/pruebas-acceso-negativo.md)
- [Autenticación y Autorización](docs/autenticacion-autorizacion.md)
- [Reporte de Crédito Consumido](docs/reporte-credito-consumido.md)

**Semana 2**

- [Justificación de Particionamiento — Cosmos DB](docs/justificacion-particionamiento-cosmos.md)
- [Justificación del Umbral de Scoring](docs/umbral-scoring.md)
- [Mensajería: Event Grid vs Service Bus](docs/mensajeria-semana2.md)
- [Prueba de Desacoplamiento (runbook)](docs/prueba-desacoplamiento.md)
- [Estrategia de Respaldo — Azure SQL](docs/estrategia-respaldo-sql.md)
- [Limitación de Tasa de la API](docs/limite-tasa-api.md)
- [Reporte de Crédito — Semana 2](docs/reporte-credito-semana2.md)
- [Lo que falta](lo-que-falta.md) — inventario honesto de pendientes por persona

**Ambas semanas**

- [Registro de Decisiones de Arquitectura (ADR)](docs/decisiones-arquitectura.md)
