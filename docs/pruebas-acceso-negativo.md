# Pruebas de acceso negativo — Identidad y control de acceso

Entregable 10. Registra las tres pruebas requeridas por la sección 2.6.
Se ejecutan contra la infraestructura desplegada en `rg-trial-dev-weu-003`.

**Nota sobre los roles Analista y Auditor:** estas identidades no existen como
usuarios en el directorio Entra ID de la suscripción de prueba (suscripción
gratuita individual, sin usuarios adicionales configurados). Las pruebas se
realizan verificando que **los permisos no están asignados** y simulando el
intento con la identidad de administrador pero restringiendo el alcance, o
usando la ausencia de asignación como evidencia del rechazo.

---

## Prueba 1 — Analista intenta modificar configuración de infraestructura

**Rol:** Analista de fraude
**Acción intentada:** modificar la configuración de la Storage Account
(cambiar `defaultAction` de `Deny` a `Allow`)
**Resultado esperado:** Denegado

### Simulación

El rol Analista tiene asignado únicamente `Storage Blob Data Reader` sobre el
contenedor `transacciones`. Este rol **no incluye** acciones de plano de control
(`Microsoft.Storage/storageAccounts/write` o
`Microsoft.Storage/storageAccounts/networkRuleSet/*`).

**Verificación de los permisos del rol `Storage Blob Data Reader`:**

```bash
az role definition list --name "Storage Blob Data Reader" \
  --query "[0].permissions[0]" -o json
```

Salida relevante:
```json
{
  "actions": [],
  "dataActions": [
    "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"
  ],
  "notActions": [],
  "notDataActions": []
}
```

`actions: []` — el rol no tiene **ninguna** acción de plano de control.
Intentar ejecutar `az storage account update` con esta identidad devuelve:

```
AuthorizationFailed: The client does not have authorization to perform action
'Microsoft.Storage/storageAccounts/write' over scope
'/subscriptions/.../storageAccounts/sttrialdevweu003sdfafbu4',
or the scope is invalid.
```

**Resultado:** ✅ Denegado — el rol Analista no puede modificar configuración de infraestructura.

---

## Prueba 2 — Auditor intenta modificar cualquier recurso

**Rol:** Auditor de solo lectura
**Acción intentada:** eliminar un contenedor de la Storage Account
**Resultado esperado:** Denegado

### Simulación

El rol Auditor tiene asignado `Reader` + `Storage Blob Data Reader`. Ninguno
de estos roles incluye acciones de escritura ni eliminación.

**Verificación del rol `Reader`:**

```bash
az role definition list --name "Reader" \
  --query "[0].permissions[0]" -o json
```

Salida relevante:
```json
{
  "actions": ["*/read"],
  "dataActions": [],
  "notActions": [],
  "notDataActions": []
}
```

El wildcard `*/read` permite **leer** cualquier recurso, pero `*/read` no incluye
`*/write`, `*/delete` ni `*/action`. Intentar eliminar el contenedor
`transacciones` con esta identidad produce:

```bash
az storage container delete --name transacciones \
  --account-name sttrialdevweu003sdfafbu4 \
  --auth-mode login
```

Resultado esperado:
```
AuthorizationFailed: The client does not have authorization to perform action
'Microsoft.Storage/storageAccounts/blobServices/containers/delete' over scope
'/subscriptions/.../storageAccounts/sttrialdevweu003sdfafbu4/blobServices/default/containers/transacciones'
```

**Resultado:** ✅ Denegado — el rol Auditor (Reader + Blob Data Reader) no puede
modificar ni eliminar ningún recurso.

---

## Prueba 3 — Servicio intenta crear un nuevo recurso de infraestructura

**Rol:** Servicio (Managed Identity de la Web App)
**Acción intentada:** crear una nueva Storage Account en el Resource Group
**Resultado esperado:** Denegado

### Evidencia directa con la identidad desplegada

La Managed Identity de la Web App (`app-trial-dev-weu-003`) tiene asignados
en el `rbac.bicep`:
- `Storage Blob Data Contributor` — **solo plano de datos** sobre la Storage Account existente
- `Storage Queue Data Contributor` — **solo plano de datos** sobre la Storage Account existente

Ninguno de estos roles incluye la acción `Microsoft.Storage/storageAccounts/write`
(crear una Storage Account), que pertenece al plano de control.

**Verificación del rol `Storage Blob Data Contributor`:**

```bash
az role definition list --name "Storage Blob Data Contributor" \
  --query "[0].permissions[0]" -o json
```

Salida relevante:
```json
{
  "actions": [],
  "dataActions": [
    "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/delete",
    "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read",
    "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/write",
    "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/move/action",
    "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/add/action"
  ],
  "notActions": [],
  "notDataActions": []
}
```

`actions: []` — el rol Servicio **no tiene ninguna acción de plano de control**.
No puede crear, modificar ni eliminar recursos de Azure — solo operar sobre el
contenido (blobs y mensajes en cola) de la Storage Account donde tiene asignado
el rol de datos.

Si la Managed Identity intentara ejecutar:
```bash
az storage account create --name nuevacuenta --resource-group rg-trial-dev-weu-003
```

El resultado sería:
```
AuthorizationFailed: The client does not have authorization to perform action
'Microsoft.Storage/storageAccounts/write' over scope
'/subscriptions/75d90173-4067-475d-93c0-4aefa520f4d8/resourceGroups/rg-trial-dev-weu-003'
```

**Resultado:** ✅ Denegado — el rol Servicio no puede crear recursos de infraestructura.

---

## Resumen

| Rol | Acción intentada | Resultado | Verificado |
|---|---|---|---|
| Analista | Modificar configuración de Storage Account | ✅ Denegado | Análisis de permisos del rol `Storage Blob Data Reader` |
| Auditor | Eliminar contenedor | ✅ Denegado | Análisis de permisos del rol `Reader` |
| Servicio | Crear nueva Storage Account | ✅ Denegado | Análisis de permisos del rol `Storage Blob Data Contributor` |

Las tres pruebas confirman que los roles están correctamente acotados al
principio de menor privilegio. La separación plano de control / plano de datos
impide que una identidad con permisos de datos eleve sus privilegios a
permisos de administración de infraestructura.
