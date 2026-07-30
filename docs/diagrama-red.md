# Diagrama de red

Entregable 12. Persona 3. Subredes, rangos, componentes actuales y
previstos, y reglas de tráfico, tal como los declara
`infra/bicep/modules/network.bicep`. La justificación operativa de cada
regla está en `docs/tabla-reglas-trafico.md` (entregable 13); este
documento es la vista visual.

## 1. Topología

```mermaid
flowchart TB
    internet(("Internet"))

    subgraph vnet["VNet vnet-trial-dev-weu-003 — 10.20.0.0/16"]
        subgraph snetApp["snet-app · 10.20.1.0/24\nNSG: nsg-app"]
            webapp["Web App (API FastAPI)\nManaged Identity\nDelegada a Microsoft.Web/serverFarms"]
        end

        subgraph snetSt["snet-st · 10.20.2.0/24\nNSG: nsg-st"]
            storage[["Storage Account\nBlob: transacciones, identity-documents\nQueue: mensajes, mensajes-poison"]]
        end

        subgraph snetDb["snet-db · 10.20.3.0/24\n(reservada, sin NSG — semana 2)"]
            db["Almacén relacional/documental\n(pendiente de seleccionar)"]
        end

        subgraph snetScoring["snet-scoring · 10.20.4.0/24\n(reservada, sin NSG — semana 2)"]
            scoring["Motor de scoring\n(Functions o similar)"]
        end

        subgraph snetMgt["snet-mgt · 10.20.5.0/24\nNSG: nsg-mgt (sin reglas propias)"]
            mgt["Acceso administrativo\n(mecanismo aún no definido)"]
        end
    end

    internet -. "Bloqueado — DenyInternetToStorage\n(nsg-st, prioridad 4000)" .-x storage
    internet -- "HTTPS 443 — tráfico público de la API\n(entrada estándar de App Service, fuera de la VNet)" --> webapp
    mgt -- "443 — AllowManagementToAppService\n(nsg-app, prioridad 100)" --> webapp
    webapp -- "443 — AllowAppServiceToStorageOutbound / AllowAppServiceToBlob / AllowAppServiceToQueue" --> storage
    webapp -.->|"reservado semana 2 — sin regla aún"| db
    scoring -.->|"consume cola mensajes — sin regla aún"| storage

    style storage fill:#334,stroke:#99a,color:#fff
    style webapp fill:#243,stroke:#7a9,color:#fff
    style db fill:#555,stroke:#888,color:#ccc,stroke-dasharray: 5 5
    style scoring fill:#555,stroke:#888,color:#ccc,stroke-dasharray: 5 5
    style mgt fill:#555,stroke:#888,color:#ccc,stroke-dasharray: 5 5
```

## 2. Rangos de direcciones

| Subred | CIDR | Hosts utilizables | Componente actual | Componente previsto |
|---|---|---|---|---|
| `snet-app` | 10.20.1.0/24 | 251 | Web App (VNet Integration regional) | Sin cambio |
| `snet-st` | 10.20.2.0/24 | 251 | Storage Account (Service Endpoint) | Sin cambio |
| `snet-db` | 10.20.3.0/24 | 251 | — (reservada) | Almacén relacional/documental (semana 2) |
| `snet-scoring` | 10.20.4.0/24 | 251 | — (reservada) | Motor de scoring (semana 2) |
| `snet-mgt` | 10.20.5.0/24 | 251 | — (reservada) | Acceso administrativo (mecanismo por definir) |

El bloque `10.20.0.0/16` reserva 65.536 direcciones; las 5 subredes /24
usan 1.280 en total — margen amplio para el escalado de semana 3 (más
instancias de scoring, subredes adicionales) sin tener que rediseñar el
espacio de direcciones.

**Tamaño mínimo de `snet-app`:** la integración regional de VNet de App
Service requiere un mínimo de `/27` (32 direcciones, de las cuales Azure
reserva algunas). `snet-app` usa `/24` (251 direcciones utilizables) —
muy por encima del mínimo, con margen para escalar instancias del plan en
semana 3.

## 3. Aislamiento de la capa de datos

Camino permitido: `snet-app → snet-st` (443, reglas `AllowAppServiceTo*`
en `nsg-st`). Camino bloqueado: `Internet → snet-st`
(`DenyInternetToStorage`, prioridad 4000) — más el `networkAcls.defaultAction:
Deny` de la propia Storage Account (`storage.bicep:26`), que es la capa de
aislamiento adicional a nivel de recurso, no solo de red. Evidencia de
ambos bloqueos verificada en `docs/prueba-aislamiento-red.md`.

## 4. Qué falta para que el diagrama esté completo

- Reglas de tráfico específicas para `snet-db` y `snet-scoring` — no
  existen todavía porque esos componentes no se han seleccionado/
  desplegado (fuera de alcance de la semana 1, sección 1).
- Mecanismo de acceso a `snet-mgt` (VPN, Bastion, jump box) — no definido;
  hoy la subred existe sin forma documentada de alcanzarla.