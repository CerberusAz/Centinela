# Convención de nombres

Entregable 6. Persona 1.

## 1. Patrón general

```
<tipo>-<prefix>-<env>-<regionShort>-<instance>[-<sufijo>]
```

Aplicado por los módulos Bicep (`infra/bicep/main.bicep` y
`infra/bicep/modules/*.bicep`), no repetido a mano en ningún recurso: cada
módulo construye el nombre a partir de los mismos cuatro parámetros que
recibe desde `main.bicep`.

| Componente | Significado | Valor usado en el despliegue actual |
|---|---|---|
| `prefix` | Proyecto/célula | `trial` |
| `env` | Ambiente | `dev` |
| `regionShort` | Código corto de región | `weu` (West Europe) |
| `instance` | Número de instancia — desambigua colisiones y despliegues paralelos | `003` |
| `sufijo` | Rol del recurso dentro de un mismo tipo (p. ej. subred, NSG) | `app`, `st`, `db`, `scoring`, `mgt` |

## 2. Prefijos por tipo de recurso

| Tipo de recurso | Prefijo | Ejemplo real desplegado | Fuente |
|---|---|---|---|
| Resource Group | `rg-` | `rg-trial-dev-weu-003` | `main.bicep:15` |
| Presupuesto (budget) | `budget-` | `budget-trial-dev-weu-003` | `budget.bicep:10` |
| Virtual Network | `vnet-` | `vnet-trial-dev-weu-003` | `network.bicep:9` |
| Subred | `snet-...-<rol>` | `snet-trial-dev-weu-003-app`, `-st`, `-db`, `-scoring`, `-mgt` | `network.bicep:165-208` |
| Network Security Group | `nsg-...-<rol>` | `nsg-trial-dev-weu-003-app`, `-st`, `-mgt` | `network.bicep:12-14` |
| App Service Plan | `plan-` | `plan-trial-dev-weu-003` | `app.bicep:12` |
| Web App (API) | `app-` | `app-trial-dev-weu-003` | `app.bicep:13` |
| Storage Account | `st` (sin guiones) + hash | `sttrialdevweu003<hash>` | `storage.bicep:10-12` |

Nota: el README de alto nivel simplifica los nombres de subred/NSG a
`snet-app`, `nsg-st`, etc. para legibilidad. El nombre real que crea el
script incluye siempre `prefix-env-regionShort-instance` completo, como se
ve en `network.bicep`.

## 3. Resolución de unicidad global

Dos tipos de recursos en Centinela requieren nombre único **en todo
Azure**, no solo dentro de la suscripción o el resource group: la cuenta
de almacenamiento y el nombre de host de la Web App
(`*.azurewebsites.net`). Se resuelven con dos mecanismos distintos, y no
son igual de robustos:

### 3.1 Storage Account — resolución automática

Regla de la plataforma: nombre en minúsculas, sin guiones ni símbolos, máx.
24 caracteres, único a nivel global. El patrón `st${prefix}${env}${regionShort}${instance}`
por sí solo no lo garantiza (dos alumnos con el mismo `prefix=trial`
colisionarían). Solución aplicada (`storage.bicep:10-12`):

```bicep
var saBaseName = 'st${prefix}${env}${regionShort}${instance}'
var storageAccountName = take('${saBaseName}${uniqueString(resourceGroup().id)}', 24)
```

`uniqueString(resourceGroup().id)` genera un hash determinístico a partir
del ID del resource group (que ya incluye la suscripción) y se trunca a 24
caracteres con `take()`. Es automático: no requiere intervención manual y
es estable entre redespliegues sobre el mismo resource group.

### 3.2 Web App — resolución manual (limitación conocida)

`app.bicep:13` no aplica ningún hash: `appName = 'app-${prefix}-${env}-${regionShort}-${instance}'`.
El nombre depende únicamente de que `instance` sea distinto al de
cualquier otra Web App ya registrada en el namespace global
`azurewebsites.net`. Esto **no está automatizado** — la evidencia del
propio historial de despliegue (`Fixing Bicep Budget Deployment Errors.md`,
líneas 201 y 245) muestra que el resource group pasó de `rg-trial-dev-weu-001`
a `-002` y finalmente a `-003` durante la misma sesión de depuración,
consistente con que `instance` tuvo que incrementarse manualmente ante
colisiones o despliegues parciales fallidos.

**Recomendación pendiente (no aplicada en este documento, se deja
registrada):** aplicar el mismo mecanismo de `uniqueString()` que ya usa
`storage.bicep` al nombre de la Web App, para que la resolución de
unicidad global sea automática en ambos casos y no dependa de que quien
ejecuta el script recuerde subir `instance`.

## 4. Recursos que no requieren unicidad global

Resource Group, VNet, subredes, NSGs, App Service Plan y Budget solo
requieren unicidad dentro de su propio scope (suscripción o resource
group), por lo que el patrón `tipo-prefix-env-regionShort-instance` es
suficiente sin hashing adicional.