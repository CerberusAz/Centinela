# Justificación de región

Entregable 3. Persona 1.

## 1. Región seleccionada: **Central US (`centralus`)**

La sección 2.2 exige justificar la región considerando **latencia**,
**disponibilidad de los servicios requeridos en las semanas 2 y 3**
(verificada, no asumida) y **costo**. Este documento registra la
evolución de la decisión de región a lo largo de los intentos reales
de despliegue de la infraestructura de semana 2.

## 2. Historial de decisiones — el camino hasta `centralus`

### Intento 1: `westeurope` (descartada — restricción de capacidad en semana 2)

Durante el despliegue de semana 1, `westeurope` fue la única región que
confirmó cuota activa para App Service Linux B1 con VNet Integration
(prueba empírica sobre 7 regiones candidatas; `eastus2` tenía cuota 0).
Al iniciar el despliegue de semana 2, con SQL Database y Cosmos DB nuevos,
Azure devolvió restricciones de capacidad física (no de cuota de
suscripción) en la región para suscripciones de prueba/estudiante:

```
RegionDoesNotAllowProvisioning: Location 'West Europe' is not accepting
creation of new Windows Azure SQL Database servers at this time.

ServiceUnavailable: Sorry, we are currently experiencing high demand in
West Europe region for the zonal redundant (Availability Zones) accounts.
```

Estos errores no son configurables ni evitables: Azure no tiene inventario
físico disponible para nuevos servidores en esa región para este tipo de
suscripción en el momento del despliegue.

### Intento 2: `northeurope` (descartada — mismo problema de capacidad)

Ante el bloqueo en `westeurope`, se intentó `northeurope` manteniendo
la proximidad geográfica europea. El resultado fue idéntico:
`RegionDoesNotAllowProvisioning` para SQL Database y `ServiceUnavailable`
para Cosmos DB.

### Intento 3: `canadacentral` (descartada — cruce de VNet ilegal)

Se intentó una estrategia de separación de capas: App Service y VNet
en `westeurope` (donde sí hay cuota) y bases de datos en `canadacentral`
(donde SQL sí se pudo crear en prueba empírica). Azure bloqueó esta
configuración con:

```
VirtualNetworkRuleBadRequest: Microsoft.Sql resources in canadacentral
cannot be ACL-ed to virtual network in westeurope. Only resources in
westeurope can be ACL-ed to virtual networks in westeurope.
```

Un Service Endpoint solo protege recursos de la misma región que la VNet.
La estrategia multi-región es incompatible con el requisito de aislamiento
de red de semana 2.

### Decisión final: `centralus`

Se ejecutó una prueba empírica sobre `centralus` verificando ambos
requisitos simultáneamente en la misma región:

```bash
# SQL Server — ÉXITO
az sql server create -g rg-test-centralus -n sql-test-centralus-987 -l centralus ...
# SQL OK in centralus

# App Service B1 Linux — ÉXITO
az appservice plan create -g rg-test-centralus -n plan-centralus --sku B1 --is-linux
# APP SERVICE OK in centralus
```

`centralus` fue la primera región en confirmar disponibilidad de capacidad
para SQL Server **y** cuota B1 Linux al mismo tiempo, que es el requisito
mínimo para que el despliegue sea viable con Service Endpoints (misma región).

## 3. Disponibilidad de servicios verificada en `centralus` (despliegue real)

| Servicio | Disponible en Central US | Estado |
|---|---|---|
| Azure SQL Database | ✅ Sí | Verificado (despliegue real) |
| Azure Cosmos DB | ✅ Sí | Verificado (despliegue real) |
| App Service Plan B1 Linux + VNet Integration | ✅ Sí | Verificado (despliegue real) |
| Azure Service Bus (Basic) | ✅ Sí | Verificado (despliegue real) |
| Azure Event Grid (topic personalizado) | ✅ Sí | Verificado (despliegue real) |
| Azure Functions (Plan B1 Linux con VNet) | ✅ Sí | Verificado (despliegue real) |

## 4. Costo

Central US pertenece a la misma banda de precios "Tier 1" que West Europe.
No hay penalización de costo significativa por el cambio de región. El
costo estimado de los componentes nuevos de semana 2 se documenta en
`docs/reporte-credito-semana2.md` §3.

## 5. Latencia

No se realizó una medición empírica de latencia. El sistema opera con
tráfico de prueba de la propia célula (no con usuarios reales), por lo
que la disponibilidad de capacidad fue el criterio eliminatorio, no la
latencia. Si en semanas posteriores se define una ubicación geográfica
real de usuarios, este criterio debe reevaluarse.

## 6. Decisión

**Central US (`centralus`, `regionShort=cus`)**, por ser la única región
verificada empíricamente con disponibilidad de capacidad simultánea para
Azure SQL Database, Cosmos DB, App Service B1 Linux con VNet Integration
y Azure Functions, con Service Endpoints funcionales para el aislamiento
de red exigido por la semana 2.