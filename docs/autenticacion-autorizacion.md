# Autenticación y autorización en Centinela

Entregable 11. Descripción conceptual de dónde ocurre la autenticación y
dónde la autorización, con ejemplos concretos aplicados al sistema Centinela
(sección 2.6).

---

## Definiciones

**Autenticación:** proceso de verificar la identidad de quien realiza una
petición. Responde a la pregunta: **"¿Quién eres?"**

**Autorización:** proceso de verificar si la identidad ya autenticada tiene
permiso para realizar la acción solicitada sobre el recurso específico.
Responde a la pregunta: **"¿Puedes hacer esto?"**

Estas son dos fases separadas y secuenciales. No hay autorización sin
autenticación previa.

---

## Ejemplo 1 — La Web App (rol Servicio) persiste una transacción en Blob Storage

### Dónde ocurre la autenticación

La Web App ejecuta `DefaultAzureCredential` (código en `api/app/storage/blob_storage.py`).
En Azure, `DefaultAzureCredential` detecta automáticamente que está corriendo
dentro de un App Service con una Managed Identity asignada y solicita un token
de acceso al **endpoint de identidad de la instancia** (IMDS — Instance Metadata
Service, `169.254.169.254`).

**Flujo de autenticación:**
```
Web App proceso Python
  └─ DefaultAzureCredential.get_token()
       └─ Petición HTTP interna al endpoint IMDS de Azure
            └─ Azure retorna un token JWT firmado por Microsoft Entra ID
                 └─ El token contiene: identidad = Object ID de la Managed Identity
```

**Quién emite el token:** Microsoft Entra ID (el directorio del tenant).
**Dónde se verifica la firma del token:** en el servicio de destino (Azure Blob Storage).

La célula **no gestiona claves ni secretos** en este flujo — Azure rota las
credenciales de la Managed Identity automáticamente.

### Dónde ocurre la autorización

El token obtenido se adjunta a la petición HTTP hacia Blob Storage
(`https://sttrialdevweu003sdfafbu4.blob.core.windows.net/transacciones/{blob}`).
Azure Blob Storage extrae el **Object ID** de la Managed Identity del token JWT
y consulta el plano de control de Azure para verificar si ese Object ID tiene
alguna asignación de rol sobre el recurso solicitado.

**Flujo de autorización:**
```
Azure Blob Storage recibe la petición con el token JWT
  └─ Extrae: principalId = Object ID de la Managed Identity de la Web App
  └─ Consulta RBAC de Azure:
       └─ ¿Tiene 'Storage Blob Data Contributor' sobre este contenedor?
            └─ Sí → 201 Created (blob escrito)
            └─ No → 403 Forbidden
```

**Quién evalúa los permisos:** el plano de datos de Azure Blob Storage, que
consulta las asignaciones de rol registradas en Azure Resource Manager
(`infra/bicep/modules/rbac.bicep` las creó al desplegar).

---

## Ejemplo 2 — Un analista accede a un documento de verificación de identidad

### Autenticación

El analista ingresa al portal de Azure (o usa az CLI) con su cuenta de
Microsoft Entra ID. Entra ID verifica su contraseña/MFA y emite un token JWT
para el analista.

**Quién se autentica:** el analista como persona, con credenciales propias.
**Diferencia con el Rol Servicio:** el analista tiene credenciales administradas
por la célula (password, MFA). El rol Servicio usa identidad gestionada —
nunca hay credencial que gestionar.

### Autorización

Para acceder al documento, el analista necesita una URL temporal (SAS token)
generada por la Web App con la identidad de la Managed Identity. Implementado
en `GET /documents/access-url` (`api/app/storage/document_storage.py::generate_read_sas_url`).

**Flujo:**
```
Analista solicita acceso al documento D del caso C
  └─ GET /documents/access-url?blob_name=D
       └─ La Web App pide un User Delegation Key a Microsoft Entra ID,
          usando su propia Managed Identity (misma autenticación del
          Ejemplo 1 — sin claves de cuenta en ningún punto)
       └─ La Web App firma un SAS con ese delegation key:
            └─ permissions: 'r' (solo lectura)
            └─ expiry: +30 minutos
            └─ resource: blob específico (no el contenedor completo)
  └─ El analista usa la URL con SAS para descargar el documento
       └─ Azure Blob Storage valida la firma del SAS contra el delegation key
            └─ 200 OK — el analista lee el documento
```

**Diferencia clave con un SAS de cuenta:** el SAS aquí lo firma un *user
delegation key* emitido por Entra ID (acción `generateUserDelegationKey`,
incluida en `Storage Blob Data Contributor`), no la clave de la cuenta de
almacenamiento. Si la Managed Identity de la Web App perdiera el permiso,
cualquier SAS ya emitido con su delegation key deja de ser válido en cuanto
ese key expira (máximo 7 días) — no hay una clave de cuenta de larga vida
que revocar.

El analista **nunca** recibe acceso permanente al contenedor. Cada acceso es
temporal y acotado al documento específico del caso. Esto cumple el requisito
de la sección 2.10: _"El acceso de los analistas se resuelve mediante un
mecanismo de acceso temporal y delegado."_

---

## Resumen: dónde ocurre cada proceso en Centinela

| Proceso | Dónde ocurre | Responsable |
|---|---|---|
| Autenticación del rol Servicio | IMDS de Azure + Microsoft Entra ID | Azure (automático, sin intervención de la célula) |
| Autenticación de usuarios (Analista, Auditor, Administrador) | Microsoft Entra ID (login con credenciales) | Azure Entra ID + la célula para la gestión de usuarios |
| Autorización del rol Servicio sobre blobs/colas | Plano de datos de Azure Storage, evaluando las asignaciones RBAC de `rbac.bicep` | Azure Resource Manager + el rol asignado por el script |
| Autorización del Analista sobre un documento específico | Firma del SAS token validada por Azure Blob Storage | La Web App (genera el SAS) + Azure (valida la firma) |
| Autorización del Auditor sobre recursos de infraestructura | Azure Resource Manager evalúa el rol `Reader` | Azure Resource Manager |

**Conclusión:** en Centinela, la autenticación siempre ocurre en Microsoft
Entra ID (emite y firma el token). La autorización ocurre en el servicio
destino (Azure Blob Storage, Azure Queue Storage, Azure Resource Manager)
que evalúa el token o la firma del SAS contra las asignaciones de rol
configuradas por el script de aprovisionamiento. La célula es responsable de
**diseñar** la matriz de roles y ejecutar el script; Azure es responsable de
**aplicar** los controles en runtime.
