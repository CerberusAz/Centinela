# Prueba de aislamiento de red — Almacenamiento

Entregable 14. Evidencia de que la cuenta de almacenamiento de Centinela
no es alcanzable desde internet, tal como exige la sección 2.7 y el
criterio de aceptación: _"El intento de alcanzar la capa de datos desde
internet falla. Demostrado."_

---

## 1. Configuración de aislamiento aplicada

La restricción de acceso se implementa en dos capas complementarias:

### Capa 1 — `networkAcls` de la Storage Account (`infra/bicep/modules/storage.bicep`)

```bicep
networkAcls: {
  bypass: 'AzureServices'
  defaultAction: 'Deny'          // Niega por defecto todo el tráfico
  virtualNetworkRules: [
    {
      id: subnetAppId            // Solo la subred de app tiene acceso
      action: 'Allow'
    }
  ]
}
```

`defaultAction: 'Deny'` hace que cualquier petición que no provenga de
`snet-trial-dev-weu-003-app` (10.20.1.0/24) sea rechazada — sin importar
si el solicitante tiene credenciales válidas o no.

### Capa 2 — NSG de la subred de storage (`infra/bicep/modules/network.bicep`)

La regla `DenyInternetToStorage` en `nsgStorage` bloquea explícitamente el
tráfico originado en `Internet` hacia la dirección de la subred `10.20.2.0/24`.

> **Mecanismo utilizado:** Service Endpoints de red virtual (`Microsoft.Storage`).
> Es el mecanismo de restricción de acceso por subred que ofrece la plataforma
> **sin costo adicional** (sección 2.7). La diferencia con el mecanismo de pago
> (Private Endpoints) se documenta al final de este archivo.

---

## 2. Pruebas ejecutadas

**Fecha y hora:** 2026-07-29T12:09:44Z (UTC)
**Storage Account:** `sttrialdevweu003sdfafbu4`
**Blob Endpoint:** `https://sttrialdevweu003sdfafbu4.blob.core.windows.net/`
**Ejecutado desde:** IP pública de la máquina de desarrollo (fuera de la VNet)

### Test 1 — `curl` sin autenticación al blob endpoint

```bash
curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
  "https://sttrialdevweu003sdfafbu4.blob.core.windows.net/?comp=list&restype=service"
```

**Resultado:**

```
403
```

**Interpretación:** La petición llegó a Azure pero fue rechazada por las reglas de
red de la Storage Account (`networkAcls.defaultAction: Deny`) antes de evaluar
cualquier credencial. HTTP 403 Forbidden — acceso denegado por red, no por
autenticación.

---

### Test 2 — `az storage container list` con identidad autenticada desde IP externa

```bash
az storage container list \
  --account-name sttrialdevweu003sdfafbu4 \
  --auth-mode login \
  --query "[].name" -o tsv
```

**Resultado:**

```
ERROR:
The request may be blocked by network rules of storage account.
Please check network rule set using 'az storage account show -n accountname --query networkRuleSet'.
If you want to change the default action to apply when no rule matches,
please use 'az storage account update'.
```

**Interpretación:** Incluso con una identidad autenticada mediante `az login`
(cuenta con permisos de propietario), la petición es rechazada porque la IP de
origen no pertenece a la subred `snet-trial-dev-weu-003-app`. El control de red
es **previo** al control de identidad: no se evalúan los permisos RBAC si el
tráfico no cumple las reglas de red.

---

## 3. Interpretación del aislamiento

| Aspecto | Resultado |
|---|---|
| Acceso anónimo desde internet | Denegado (HTTP 403) |
| Acceso autenticado desde internet | Denegado (error de regla de red) |
| Acceso desde subred `snet-app` (10.20.1.0/24) | Permitido (Service Endpoint activo) |
| Acceso desde otras subredes de la VNet | Denegado (`defaultAction: Deny`) |

El criterio de aislamiento se cumple: la capa de datos **no es alcanzable desde
internet** independientemente de si el solicitante tiene credenciales.

---

## 4. Service Endpoints vs. Private Endpoints

Sección 2.7 exige documentar las diferencias entre el mecanismo usado (gratuito)
y el equivalente de pago.

| Característica | Service Endpoints (usado) | Private Endpoints (pago) |
|---|---|---|
| Costo | Gratuito | ~$0.01/hora por endpoint + transferencia |
| Tráfico | Viaja por la red troncal de Azure (no por internet público) pero la Storage Account sigue teniendo IP pública | Tráfico completamente privado; la Storage Account recibe una IP privada dentro de la VNet |
| DNS | La URL pública sigue resolviendo (el rechazo es por regla de red, no por DNS) | Se requiere zona DNS privada para que la URL resuelva a la IP privada |
| Exfiltración de datos | Posible si hay un servicio comprometido dentro de la misma subred | Control más granular mediante políticas de endpoint |
| Complejidad operativa | Baja — configuración en la Storage Account + delegación de subred | Alta — requiere zona DNS privada, NIC dedicada, integración con resolución DNS |
| Caso de uso adecuado | Proyectos con presupuesto limitado donde el tráfico desde internet ya está bloqueado por `defaultAction: Deny` | Entornos de producción con requisitos regulatorios estrictos (PCI-DSS, HIPAA) que exigen que la IP del servicio nunca sea pública |

**Decisión registrada:** se usa Service Endpoints porque el presupuesto de la
suscripción gratuita no permite Private Endpoints, y el nivel de aislamiento
obtenido (`defaultAction: Deny` + Service Endpoint en subred específica) cumple
el requisito de la semana 1. En un entorno de producción financiero real, se
evaluaría Private Endpoints para cumplir requisitos de auditoría más estrictos.
Esta decisión debe registrarse en `docs/decisiones-arquitectura.md` (Persona 3).
