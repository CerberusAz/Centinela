# Informe de cuotas — Centinela Semana 1

Entregable 2. Consulta ejecutada sobre la suscripción activa el 2026-07-29
mediante `az vm list-usage --location westeurope`. Esta información condiciona
el diseño de las semanas 2 y 3.

**Suscripción:** Azure subscription 1 (`75d90173-4067-475d-93c0-4aefa520f4d8`)
**Región evaluada:** West Europe (`westeurope`)
**Fecha de consulta:** 2026-07-29T12:09Z (UTC)

---

## 1. Capacidad de cómputo disponible

Las cuotas relevantes para el proyecto son las de las familias de VMs que
usa App Service. App Service PaaS **no consume cuota de VM**; consume cuota
de la familia del plan (`Standard BS Family` para el plan B1). Las cuotas de
VM aplican solo si se despliegan máquinas virtuales directamente — lo que
Centinela no hace.

| Recurso | Usado | Límite | Estado |
|---|---|---|---|
| Total Regional vCPUs | 0 | 4 | ✅ Disponible |
| Standard BS Family vCPUs | 0 | 4 | ✅ Disponible — aplica a B1 |
| Standard Basv2 Family vCPUs | 0 | 4 | ✅ Disponible |
| Standard Bsv2 Family vCPUs | 0 | 4 | ✅ Disponible |
| Standard DSv3 Family vCPUs | 0 | 4 | ✅ Disponible |
| Standard FSv2 Family vCPUs | 0 | 4 | ✅ Disponible |
| Standard F Family vCPUs | 0 | 4 | ✅ Disponible |

**Conclusión de cómputo:** la cuota de la familia BS (que incluye el tamaño
B1 que usa el App Service Plan) tiene 4 vCPUs disponibles y ninguna en uso.
El despliegue de un App Service Plan B1 Linux consume 1 vCPU de esta cuota.

---

## 2. Disponibilidad del servicio de reconocimiento documental (Document Intelligence)

El servicio relevante para la semana 2/3 es **Azure AI Document Intelligence**
(anteriormente llamado Form Recognizer, identificador de recurso: `FormRecognizer`).

**Verificación:**

```bash
az provider show --namespace Microsoft.CognitiveServices \
  --query "resourceTypes[?resourceType=='accounts'].locations" -o tsv
```

**Resultado:** West Europe aparece en la lista de regiones disponibles para
`Microsoft.CognitiveServices/accounts`:

```
... West US  West US 2  West Europe  North Europe  Southeast Asia ...
```

**Verificación del kind FormRecognizer:**

```bash
az cognitiveservices account list-kinds -o tsv | grep -i "FormRecognizer"
```

Salida: `FormRecognizer` — el kind está disponible en la suscripción.

| Servicio | Disponible en West Europe | Nivel gratuito (F0) |
|---|---|---|
| Azure AI Document Intelligence (FormRecognizer) | ✅ Sí | ✅ F0 disponible para pruebas |
| Azure Cognitive Services (multi-servicio) | ✅ Sí | — |

**Nota de diseño para semana 2/3:** el nivel F0 de Document Intelligence
tiene límites de uso (500 páginas/mes, 20 transacciones/minuto). Para el
volumen de la célula en 21 días es suficiente. Si el análisis de documentos
requiere más capacidad, el nivel S0 está disponible en West Europe.

---

## 3. Servicios con cuota cero

Los siguientes servicios tienen cuota 0/0 en la suscripción de prueba.
Son familias de VMs de alto rendimiento o confidenciales que Azure no
habilita en suscripciones gratuitas.

| Servicio | Cuota | Impacto en Centinela |
|---|---|---|
| Dedicated vCPUs | 0/0 | ❌ Sin impacto — Centinela no usa VMs dedicadas |
| Standard DCSv2 Family (Confidential VMs) | 0/0 | ❌ Sin impacto — no aplica al proyecto |
| Standard H Family vCPUs (HPC) | 0/0 | ❌ Sin impacto — no aplica al proyecto |
| Standard HBv3/v4/v5 Family (HPC) | 0/0 | ❌ Sin impacto — no aplica al proyecto |
| Standard ECadsv6/ECasv6 (Confidential) | 0/0 | ❌ Sin impacto — no aplica al proyecto |
| Standard EIADSv5 Family | 0/0 | ❌ Sin impacto — no aplica al proyecto |
| Standard FXMDVS Family | 0/0 | ❌ Sin impacto — no aplica al proyecto |

**Conclusión:** ninguno de los servicios con cuota cero es requerido por la
arquitectura de Centinela en ninguna de las tres semanas. La arquitectura PaaS
(App Service, Storage, Cognitive Services) no depende de estas familias.

---

## 4. Límite de gasto de la suscripción

El límite de gasto de Azure es un control del portal que **no se puede verificar
ni configurar mediante CLI**. Debe verificarse manualmente:

**Pasos para verificar manualmente:**

1. Ingresar al portal de Azure: [portal.azure.com](https://portal.azure.com)
2. Ir a **Suscripciones** → seleccionar `Azure subscription 1`
3. En el menú lateral, buscar **Límite de gasto** o **Spending limit**
4. Verificar que el límite esté **activo** (no deshabilitado)

**Comportamiento documentado al agotarse el crédito:** cuando el crédito de la
suscripción gratuita se agota, Azure **suspende todos los recursos en ejecución**
(los detiene, no los elimina). Los datos persisten hasta que se reactiva la
suscripción mediante actualización a pago por uso o recarga de crédito. Los recursos
no se eliminan automáticamente — se mantienen en estado suspendido durante un
período de gracia (típicamente 30-60 días según los términos de la suscripción).

**Alertas de presupuesto configuradas en código** (`infra/bicep/modules/budget.bicep`):

| Umbral | Tipo | Contacto |
|---|---|---|
| 50% del presupuesto ($70 de $140) | Consumido real | san.mu.zap@gmail.com |
| 80% del presupuesto ($112 de $140) | Consumido real | san.mu.zap@gmail.com |
| 100% del presupuesto (proyectado) | Proyección | san.mu.zap@gmail.com |

---

## 5. Impacto en el diseño de las semanas 2 y 3

| Decisión | Verificación | Estado |
|---|---|---|
| App Service Plan B1 en West Europe | Familia BS con cuota 4 vCPU disponible | ✅ Viable |
| Document Intelligence para verificación documental | Disponible en West Europe, kind FormRecognizer activo | ✅ Viable |
| Sin VMs propias (arquitectura 100% PaaS) | No depende de cuotas de VM | ✅ Sin riesgo |
| Azure Cosmos DB / SQL (semana 2) | No evaluado en este informe — verificar en semana 2 | ⚠️ Pendiente |
