# Matriz de roles y permisos — Centinela

Entregable 8. Define los cuatro roles de la sección 2.6, sus permisos y la
operación del sistema que justifica cada uno. Aplicando el principio de
menor privilegio.

---

## Principios aplicados

- **Menor privilegio:** cada rol recibe solo los permisos que necesita para
  cumplir sus funciones, nada más.
- **Plano de control vs. plano de datos:** se distingue explícitamente entre
  permisos de administración del recurso (plano de control) y permisos sobre
  el contenido del recurso (plano de datos).
- **Sin permisos sin operación asociada:** todo permiso de la matriz tiene una
  operación concreta del sistema que lo justifica. Un permiso sin operación se
  retira (sección 2.6).

---

## Tabla de roles y permisos

| Rol | Recurso | Plano | Rol integrado asignado | Operación del sistema que lo justifica |
|---|---|---|---|---|
| **Servicio** (Managed Identity de la Web App) | Storage Account — contenedor `transacciones` | Datos | `Storage Blob Data Contributor` | Persistir la transacción cruda al recibirla (API de ingesta, paso 3 de la secuencia recibir→validar→persistir→responder) |
| **Servicio** (Managed Identity de la Web App) | Storage Account — cola `mensajes` | Datos | `Storage Queue Data Contributor` | Publicar el evento `transaction.received` en la cola tras persistir (punto de inserción semana 2, ya cableado en `IngestionService.ingest()`) |
| **Servicio** (Managed Identity de la Web App) | Storage Account — contenedor `identity-documents` | Datos | `Storage Blob Data Contributor` | Cargar documentos de verificación de identidad (endpoint `POST /documents`, sección 2.10) |
| **Administrador** | Subscription / Resource Group | Control | `Owner` o `Contributor` | Gestionar el ciclo de vida de los recursos: crear, modificar, eliminar (solo personal de infraestructura) |
| **Administrador** | Storage Account | Control | `Storage Account Contributor` | Modificar configuración de la Storage Account (reglas de red, redundancia, lifecycle) |
| **Analista de fraude** | Storage Account — contenedor `identity-documents` | Datos | _SAS token delegado_ (sin rol RBAC permanente) | Acceder temporalmente a documentos de verificación de identidad para el análisis de un caso. El acceso se realiza mediante un mecanismo de acceso temporal y delegado (SAS token), no mediante un rol RBAC permanente |
| **Analista de fraude** | Storage Account — contenedor `transacciones` | Datos | `Storage Blob Data Reader` | Consultar la transacción cruda asociada a un caso de fraude |
| **Auditor de solo lectura** | Storage Account | Datos + Control | `Reader` + `Storage Blob Data Reader` | Auditar configuración de recursos y contenido de los contenedores sin capacidad de modificar nada |
| **Auditor de solo lectura** | Resource Group / Subscription | Control | `Reader` | Consultar el estado de los recursos de infraestructura para auditoría |

---

## Detalle del Rol Servicio

El rol Servicio se implementa mediante una **identidad gestionada asignada por
el sistema** (`SystemAssigned`) en la Web App (`infra/bicep/modules/app.bicep`):

```bicep
identity: {
  type: 'SystemAssigned'
}
```

Las asignaciones de rol se crean desde el script de aprovisionamiento
(`infra/bicep/modules/rbac.bicep`):

```bicep
// Storage Blob Data Contributor — para persistir transacciones y cargar documentos
var blobContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

// Storage Queue Data Contributor — para publicar eventos en la cola
var queueContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
```

**¿Por qué `Storage Blob Data Contributor` y no `Storage Blob Data Owner`?**
`Storage Blob Data Contributor` permite leer, escribir y eliminar blobs pero
**no puede gestionar permisos RBAC sobre el contenedor** (eso requiere
`Storage Blob Data Owner`). La API de ingesta nunca necesita modificar
permisos — solo leer y escribir blobs. Asignar `Owner` sería exceso de
privilegio.

**¿Por qué no claves de cuenta ni connection strings?**
Las claves de cuenta dan acceso total a toda la Storage Account
(todos los contenedores, todas las colas) sin control de plano de datos RBAC.
La identidad gestionada, en cambio, permite restringir el acceso por contenedor
y auditarlo en los logs de Entra ID. Además, las claves requieren rotación
manual y tienen alto riesgo de exposición en código o variables de entorno.

---

## Roles fuera de alcance en semana 1

Los roles **Analista de fraude** y **Auditor** requieren cuentas de usuario
en Microsoft Entra ID (directorio del tenant). Su configuración completa
(creación de usuarios, asignación de roles) es responsabilidad de la
Persona 2 del equipo y está pendiente de ejecución manual en el portal de
Entra ID / Azure RBAC. Los permisos definidos en esta tabla son el diseño;
la asignación efectiva se documenta en `docs/pruebas-acceso-negativo.md`.
