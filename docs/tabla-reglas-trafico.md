# Tabla de reglas de tráfico

Entregable 13. Persona 3. Reglas de los Network Security Group definidos
en `infra/bicep/modules/network.bicep`, bajo el criterio de denegar por
defecto exigido por la sección 2.7. Ninguna regla admite origen
`0.0.0.0/0` / `Any`.

## NSG `nsg-...-app` (subred `snet-...-app`, 10.20.1.0/24)

| Regla | Dirección | Prioridad | Origen | Destino | Puerto | Justificación operativa |
|---|---|---|---|---|---|---|
| `AllowManagementToAppService` | Inbound | 100 | `10.20.5.0/24` — subred de gestión (`mgt`) | `10.20.1.0/24` — subred de aplicación | 443 | Permite administración/diagnóstico de la Web App desde la subred de gestión reservada. |
| `AllowAppServiceToStorageOutbound` | Outbound | 100 | `10.20.1.0/24` — subred de aplicación | `10.20.2.0/24` — subred de almacenamiento | 443 | Habilita que la API alcance Blob y Queue Storage — requisito de la sección 2.9 paso 3 (persistir la transacción cruda) y 2.11 (escribir en la cola de ingesta). |
| `DenyAllVnetInbound` | Inbound | 4095 | `VirtualNetwork` (cualquier subred interna) | `*` | `*` | Denegar por defecto: bloquea cualquier tráfico este-oeste hacia la subred de aplicación que no esté explícitamente permitido arriba. |

## NSG `nsg-...-st` (subred `snet-...-st`, 10.20.2.0/24)

| Regla | Dirección | Prioridad | Origen | Destino | Puerto | Justificación operativa |
|---|---|---|---|---|---|---|
| `AllowAppServiceToBlob` | Inbound | 100 | `10.20.1.0/24` — subred de aplicación | `10.20.2.0/24` — subred de almacenamiento | 443 | Permite guardar la transacción cruda tras validarla (sección 2.9, paso 3). |
| `AllowAppServiceToQueue` | Inbound | 110 | `10.20.1.0/24` — subred de aplicación | `10.20.2.0/24` — subred de almacenamiento | 443 | Permite escribir/leer en la cola de ingesta `mensajes` (sección 2.11). |
| `DenyInternetToStorage` | Inbound | 4000 | `Internet` | `10.20.2.0/24` — subred de almacenamiento | `*` | Cumple el requisito no negociable de la sección 2.7: los almacenes de datos no deben ser alcanzables desde internet. Evidencia de esta regla en acción en `docs/prueba-aislamiento-red.md`. |
| `DenyStorageToInternet` | Outbound | 4000 | `10.20.2.0/24` — subred de almacenamiento | `Internet` | `*` | Evita exfiltración de datos desde la cuenta de almacenamiento hacia internet. |
| `DenyAllVnetInbound` | Inbound | 4095 | `VirtualNetwork` (cualquier subred interna) | `*` | `*` | Denegar por defecto: bloquea cualquier tráfico este-oeste hacia storage que no esté explícitamente permitido arriba (p. ej. una futura subred comprometida no listada). |

## NSG `nsg-...-mgt` (subred `snet-...-mgt`, 10.20.5.0/24)

`network.bicep:146-152` la declara con `securityRules: []` — sin reglas
personalizadas. Rige únicamente el conjunto de reglas por defecto de la
plataforma (`AllowVnetInBound`/`AllowAzureLoadBalancerInBound` en
prioridad 65000-65001, `DenyAllInBound` en 65500), que ya deniegan tráfico
entrante desde internet.

**Nota operativa:** en la semana 1 ningún componente usa esta subred
todavía — está reservada. No se le añaden reglas hasta que se defina el
mecanismo real de acceso administrativo (VPN, Azure Bastion o jump box),
fuera del alcance de esta semana.

## Subredes sin NSG asignado (reservadas para semana 2)

`snet-...-db` (10.20.3.0/24) y `snet-...-scoring` (10.20.4.0/24) no tienen
NSG en `network.bicep` — se crean vacías, sin recursos ni reglas, para
reservar el rango de direcciones. La sección 2.7 exige diseñar la red
"incluyendo los previstos para las semanas 2 y 3", pero las reglas de
tráfico específicas para el almacén relacional/documental y el motor de
scoring solo pueden definirse cuando esos componentes existan.