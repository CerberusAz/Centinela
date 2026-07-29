# Centinela — Semana 1: Arquitectura de Ingesta e Infraestructura Base

Sistema de ingesta de transacciones financieras resiliente, seguro y desacoplado sobre **Microsoft Azure**, enfocado en control de costos, seguridad de red y validación de contrato para la detección asíncrona de fraude.

---

## 🛠️ Tech Stack & Tecnologías

- **Lenguaje y Framework API**: Python 3.11+ / FastAPI (Uvicorn / Gunicorn)
- **Infraestructura como Código (IaC)**: Azure Bicep (Módulos parametrizados e idempotentes) + Shell Scripts (`az CLI`)
- **Cómputo & Plataforma**: Azure App Service (Plan B1 Linux, Python 3.11)
- **Redes & Seguridad**: Azure Virtual Network (VNet), Network Security Groups (NSGs), VNet Regional Integration, Service Endpoints (`Microsoft.Storage`)
- **Almacenamiento**: Azure Blob Storage (Blobs & Containers), Azure Storage Queues
- **Gestión de Identidad & RBAC**: Microsoft Entra ID, System-Assigned Managed Identity, Azure Role Assignments (RBAC de plano de datos)
- **Pruebas y Calidad**: Pytest, Pydantic v2 (Validación estricta de contrato), `python-multipart`

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
| **Storage Queue** | Standard Queue | `mensajes` | Cola de desacoplamiento para el motor de scoring |
| **Virtual Network** | `/16` (10.20.0.0/16) | `vnet-trial-dev-weu-003` | Red privada de aislamiento |
| **Presupuesto** | Consumption Budget | `budget-trial-dev-weu-003` | Alertas de consumo ($70, $112, 100% proyectado) |

---

### 2. Topology de Subredes y Reglas NSG (Acceso de Red)

La red `10.20.0.0/16` está segmentada en 5 subredes preparadas para el escalado de las semanas 2 y 3, bajo la política estricta de **Denegar por Defecto**:

```
VNet 10.20.0.0/16
 ├── snet-app     (10.20.1.0/24) -> Delegada a App Service (VNet Integration)
 ├── snet-st      (10.20.2.0/24) -> Storage Account (Service Endpoint: Microsoft.Storage)
 ├── snet-db      (10.20.3.0/24) -> Reservada para BBDD Relacional (Semana 2)
 ├── snet-scoring (10.20.4.0/24) -> Reservada para Motor de Scoring / Functions (Semana 2)
 └── snet-mgt     (10.20.5.0/24) -> Subred de Gestión / Administración
```

#### Reglas de Tráfico (Network Security Groups)

- **`nsg-app` (Subred de Aplicaciones - 10.20.1.0/24)**
  - `Inbound`: `AllowManagementToAppService` (TCP 443 desde `10.20.5.0/24`). `DenyAllVnetInbound` (Priority 4095).
  - `Outbound`: `AllowAppServiceToStorageOutbound` (TCP 443 hacia `10.20.2.0/24`).

- **`nsg-st` (Subred de Almacenamiento - 10.20.2.0/24)**
  - `Inbound`: `AllowAppServiceToBlob` y `AllowAppServiceToQueue` (TCP 443 desde `10.20.1.0/24`). `DenyInternetToStorage` (Priority 4000: Bloquea todo tráfico desde `Internet`). `DenyAllVnetInbound` (Priority 4095).
  - `Outbound`: `DenyStorageToInternet` (Priority 4000: Bloquea salidas hacia `Internet`).

- **Aislamiento de Almacenamiento**:
  - `networkAcls.defaultAction: Deny` en la Storage Account.
  - El acceso a datos desde internet es **rechazado (HTTP 403 / Network Rule Error)** incluso para usuarios autenticados. Únicamente el tráfico originado en `snet-app` vía Service Endpoint es procesado.

---

## 💰 Análisis de Costos & Presupuesto

- **Límite de Consumo Semana 1**: < $20 USD.
- **Presupuesto Mensual Configurado**: $140 USD.

### Estructura de Costos Estimada (21 Días del Proyecto)

| Componente | Nivel / SKU | Estimado (21 Días) | Estrategia de Ahorro |
|---|---|---|---|
| **App Service Plan** | Basic (B1) | ~$9.50 - $13.50 USD | Se apaga al final de la jornada con `./infra/shutdown.sh` |
| **Storage Account** | Standard_LRS | ~$0.10 - $0.50 USD | Nivel LRS (más económico) + Lifecycle policy activa |
| **VNet / Subredes / NSGs** | Estándar | $0.00 USD | Gratuitos en Azure |
| **Service Endpoints** | Red | $0.00 USD | Sin cargo adicional (alternativa costo $0 vs Private Endpoints) |
| **Total Estimado Semana 1** | — | **~$10.00 - $14.00 USD** | **Dentro del límite de $20 USD** |

---

## 📁 Estructura del Repositorio

```text
├── Azure-Semana1.md             # Especificación oficial de requerimientos
├── README.md                    # Documentación principal del sistema
├── api/                         # Código fuente de la API FastAPI
│   ├── app/
│   │   ├── api/routes.py        # Endpoints HTTP (POST /transactions, GET /transactions/{id}, POST /documents)
│   │   ├── core/config.py       # Configuración externalizada (variables CENTINELA_)
│   │   ├── models/              # Modelos Pydantic (contrato de transacción y validaciones)
│   │   ├── services/ingestion.py# Lógica de orquestación de ingesta e idempotencia
│   │   ├── storage/             # Adaptadores de almacenamiento (Blob & Memory & Documents)
│   │   └── messaging/           # Publisher de eventos (No-Op para desacoplamiento)
│   ├── tests/                   # Suite de pruebas automatizadas (Pytest)
│   └── requirements.txt         # Dependencias Python
├── docs/                        # Entregables formales de arquitectura
│   ├── informe-cuotas.md        # Entregable 2: Cuotas de suscripción y servicios
│   ├── prueba-aislamiento-red.md# Entregable 14: Evidencia de aislamiento de storage
│   ├── garantias-entrega-cola.md# Entregable 22: Comportamiento y política de cola
│   ├── matriz-roles-permisos.md # Entregable 8: Definición de roles y menor privilegio
│   ├── pruebas-acceso-negativo.md # Entregable 10: Evidencia de pruebas negativas RBAC
│   ├── autenticacion-autorizacion.md # Entregable 11: Nota conceptual Entra ID / RBAC
│   ├── contrato-transaccion.md  # Entregable 15: Contrato y las 4 decisiones
│   └── decisiones-arquitectura.md # Entregable 25: Registro de decisiones (ADR)
└── infra/                       # Infraestructura como Código (Bicep + Bash)
    ├── bicep/                   # Plantillas Bicep (main, app, network, storage, rbac, budget)
    ├── deploy-all.sh            # Script maestro de aprovisionamiento
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

Para correr la API localmente en modo desacoplado (en memoria, sin credenciales de Azure):

```bash
cd api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Iniciar servidor local
uvicorn app.main:app --reload --port 8000
```

Ejecutar suite de pruebas:

```bash
python -m pytest -v
```

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

## 📚 Documentación Técnica de Referencia

- [Contrato de Transacción](docs/contrato-transaccion.md)
- [Informe de Cuotas](docs/informe-cuotas.md)
- [Prueba de Aislamiento de Red](docs/prueba-aislamiento-red.md)
- [Garantías de Entrega en Cola](docs/garantias-entrega-cola.md)
- [Matriz de Roles y Permisos RBAC](docs/matriz-roles-permisos.md)
- [Bitácora de Pruebas Negativas](docs/pruebas-acceso-negativo.md)
- [Registro de Decisiones de Arquitectura (ADR)](docs/decisiones-arquitectura.md)
