#!/bin/bash

# 03-create-storage.sh
# Script para crear cuenta de almacenamiento, contenedores, colas y configurar el firewall
#
# ======================================================================================================
# DOCUMENTACIÓN: Service Endpoint vs Private Endpoint
# ======================================================================================================
# 1. Service Endpoint (Mecanismo implementado aquí - Sin costo adicional):
#    - Permite que el tráfico desde la red virtual hacia la cuenta de almacenamiento pase 
#      directamente por la red troncal de Azure (Azure backbone).
#    - La cuenta de almacenamiento sigue teniendo una dirección IP pública, pero el firewall 
#      nativo bloquea todo el tráfico que no provenga de la subred especificada.
#    - Es fácil de configurar y NO tiene costos adicionales asociados.
#
# 2. Private Endpoint (Mecanismo de pago - No implementado aquí):
#    - Asigna una dirección IP privada (NIC) de tu propia red virtual a la cuenta de almacenamiento.
#    - Todo el tráfico de la VNet hacia el almacenamiento pasa exclusivamente por esa IP privada, 
#      eliminando la necesidad de que la cuenta de almacenamiento sea accesible vía IP pública.
#    - Tiene un costo asociado por hora por tener el Endpoint activo, y un costo adicional por 
#      los GB de datos procesados (entrantes y salientes).
#    - Provee mayor nivel de seguridad y permite conectividad directa desde redes On-Premises.
# ======================================================================================================

PROJECT_PREFIX="${PROJECT_PREFIX:-trial}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
INSTANCE="${INSTANCE:-001}"
REGION_SHORT="${REGION_SHORT:-eus2}"
LOCATION="${LOCATION:-eastus2}"

RG_NAME="rg-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}"
VNET_NAME="vnet-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}"
SNET_APP="snet-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}-app"

SA_BASE_NAME="st${PROJECT_PREFIX}${ENVIRONMENT}${REGION_SHORT}${INSTANCE}"

BLOB_CONTAINER_NAME="transacciones"
IDENTITY_CONTAINER_NAME="identity-documents"
QUEUE_NAME="mensajes"

# 1. Crear o reutilizar Storage Account (Inicialmente con acceso Allow)
EXISTING_SA=$(az storage account list -g $RG_NAME --query "[?starts_with(name, '${SA_BASE_NAME}')].name" -o tsv | head -n 1)

if [ -n "$EXISTING_SA" ]; then
    echo "El Storage Account '$EXISTING_SA' ya existe. Usando este..."
    STORAGE_ACCOUNT_NAME=$EXISTING_SA
else
    # Generar un sufijo aleatorio para asegurar que el nombre de Storage Account sea único (Max 24 chars, solo minúsculas y números)
    RAND_STR=$(LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom | head -c 5)
    STORAGE_ACCOUNT_NAME="${SA_BASE_NAME}${RAND_STR}"
    echo "Creando Storage Account: $STORAGE_ACCOUNT_NAME..."
    az storage account create \
        --name $STORAGE_ACCOUNT_NAME \
        --resource-group $RG_NAME \
        --location $LOCATION \
        --sku Standard_LRS \
        --kind StorageV2 \
        --https-only true \
        --min-tls-version TLS1_2 \
        --default-action Allow
fi

# 2. Obtener cadena de conexión para operaciones sobre los datos
echo "Obteniendo Connection String del Storage Account..."
CONN_STR=$(az storage account show-connection-string --name $STORAGE_ACCOUNT_NAME --resource-group $RG_NAME --query connectionString -o tsv)

# 3. Crear Blob Container y Queue
if [ "$(az storage container exists --name $BLOB_CONTAINER_NAME --connection-string "$CONN_STR" --query exists -o tsv 2>/dev/null)" != "true" ]; then
    echo "Creando Blob Container: $BLOB_CONTAINER_NAME..."
    az storage container create \
        --name $BLOB_CONTAINER_NAME \
        --connection-string "$CONN_STR" \
        --public-access off
else
    echo "El Blob Container '$BLOB_CONTAINER_NAME' ya existe."
fi

if [ "$(az storage container exists --name $IDENTITY_CONTAINER_NAME --connection-string "$CONN_STR" --query exists -o tsv 2>/dev/null)" != "true" ]; then
    echo "Creando Blob Container: $IDENTITY_CONTAINER_NAME..."
    az storage container create \
        --name $IDENTITY_CONTAINER_NAME \
        --connection-string "$CONN_STR" \
        --public-access off
else
    echo "El Blob Container '$IDENTITY_CONTAINER_NAME' ya existe."
fi

if [ "$(az storage queue exists --name $QUEUE_NAME --connection-string "$CONN_STR" --query exists -o tsv 2>/dev/null)" != "true" ]; then
    echo "Creando Storage Queue: $QUEUE_NAME..."
    az storage queue create \
        --name $QUEUE_NAME \
        --connection-string "$CONN_STR"
else
    echo "La Storage Queue '$QUEUE_NAME' ya existe."
fi

# 4. Configurar Service Endpoints en las Subredes
# Habilitamos Service Endpoints UNICAMENTE en 'snet-app' 
# cumpliendo el Principio de Menor Privilegio (ya que es el único que origina peticiones).
echo "Habilitando Service Endpoints (Microsoft.Storage) en la subred de AppService..."
az network vnet subnet update -g $RG_NAME --vnet-name $VNET_NAME -n "$SNET_APP" --service-endpoints Microsoft.Storage

# 5. Configurar el Firewall del Storage Account
echo "Configurando Firewall del Storage para permitir tráfico SOLO desde la subred autorizada..."
SUBNET_ID_APP=$(az network vnet subnet show -g $RG_NAME -n "$SNET_APP" --vnet-name $VNET_NAME --query id -o tsv)

az storage account network-rule add -g $RG_NAME --account-name $STORAGE_ACCOUNT_NAME --subnet $SUBNET_ID_APP

# 6. Restringir todo el tráfico exterior (Activar el Firewall de forma estricta)
echo "Aplicando regla de Denegar todo el tráfico externo por defecto..."
az storage account update --name $STORAGE_ACCOUNT_NAME --resource-group $RG_NAME --default-action Deny

# 7. Configurar Lifecycle Management (Gestión del ciclo de vida)
echo "Configurando reglas de Lifecycle Management..."
cat <<EOF > lifecycle_policy.json
{
  "rules": [
    {
      "enabled": true,
      "name": "cost-optimization-rule",
      "type": "Lifecycle",
      "definition": {
        "actions": {
          "baseBlob": {
            "tierToCool": {
              "daysAfterModificationGreaterThan": 30
            },
            "tierToArchive": {
              "daysAfterModificationGreaterThan": 90
            },
            "delete": {
              "daysAfterModificationGreaterThan": 365
            }
          }
        },
        "filters": {
          "blobTypes": [
            "blockBlob"
          ],
          "prefixMatch": [
            "${BLOB_CONTAINER_NAME}/",
            "${IDENTITY_CONTAINER_NAME}/"
          ]
        }
      }
    }
  ]
}
EOF

az storage account management-policy create \
    --account-name $STORAGE_ACCOUNT_NAME \
    --resource-group $RG_NAME \
    --policy @lifecycle_policy.json

# Limpiar archivo temporal
rm -f lifecycle_policy.json

echo "================================================================"
echo "CREACIÓN Y CONFIGURACIÓN FINALIZADA DE FORMA SEGURA"
echo "Storage Account: $STORAGE_ACCOUNT_NAME"
echo "⚠️  NOTA: El App Service debe autenticarse contra este Storage"
echo "utilizando Identidad Gestionada (DefaultAzureCredential) y RBAC."
echo "================================================================"
