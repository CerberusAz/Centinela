#!/bin/bash

# 02-create-nsg.sh
# Script para crear NSGs, asignar reglas y asociarlas a las subnets

# Variables (Deben coincidir con las del script 01)
PROJECT_PREFIX="${PROJECT_PREFIX:-trial}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
INSTANCE="${INSTANCE:-001}"
REGION_SHORT="${REGION_SHORT:-eus2}"

RG_NAME="rg-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}"
VNET_NAME="vnet-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}"

SNET_APP="snet-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}-app"
SNET_STORAGE="snet-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}-st"
SNET_MGT="snet-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}-mgt"

NSG_APP="nsg-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}-app"
NSG_STORAGE="nsg-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}-st"
NSG_MGT="nsg-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}-mgt"

# Funciones auxiliares de idempotencia
safe_create_nsg() {
    local nsg_name=$2
    if ! az network nsg show -g $RG_NAME -n $nsg_name > /dev/null 2>&1; then
        echo "Creando NSG: $nsg_name..."
        az network nsg create -g $RG_NAME -n $nsg_name
    else
        echo "El NSG '$nsg_name' ya existe."
    fi
}

safe_create_nsg_rule() {
    local nsg_name=$1
    local rule_name=$3
    shift 3
    if ! az network nsg rule show -g $RG_NAME --nsg-name $nsg_name -n $rule_name > /dev/null 2>&1; then
        echo "Creando Regla: $rule_name en $nsg_name..."
        az network nsg rule create -g $RG_NAME --nsg-name $nsg_name -n $rule_name "$@"
    else
        echo "La Regla '$rule_name' en '$nsg_name' ya existe."
    fi
}

# 1. Crear los contenedores de NSG
echo "Verificando/Creando Network Security Groups (Contenedores)..."
safe_create_nsg -g $RG_NAME -n "$NSG_APP"
safe_create_nsg -g $RG_NAME -n "$NSG_STORAGE"
safe_create_nsg -g $RG_NAME -n "$NSG_MGT"

# 2. Asignar Reglas al NSG de Storage (nsg-storage)
echo "Asignando reglas a $NSG_STORAGE..."

# PERMITIR: Origen: AppService -> Destino: Storage | Puerto: 443 | Justificación: Guardar transacciones.
safe_create_nsg_rule "$NSG_STORAGE" \
    -n AllowAppServiceToBlob \
    --priority 100 \
    --direction Inbound \
    --access Allow \
    --protocol Tcp \
    --source-address-prefixes 10.20.1.0/24 \
    --source-port-ranges '*' \
    --destination-address-prefixes 10.20.2.0/24 \
    --destination-port-ranges 443 \
    --description "Guardar transacciones"

# PERMITIR: Origen: AppService -> Destino: Queue | Puerto: 443 | Justificación: Enviar mensajes.
safe_create_nsg_rule "$NSG_STORAGE" \
    -n AllowAppServiceToQueue \
    --priority 110 \
    --direction Inbound \
    --access Allow \
    --protocol Tcp \
    --source-address-prefixes 10.20.1.0/24 \
    --source-port-ranges '*' \
    --destination-address-prefixes 10.20.2.0/24 \
    --destination-port-ranges 443 \
    --description "Enviar mensajes"

# DENEGAR: Origen: Internet -> Destino: Storage | Puerto: Todos | Justificación: Bloqueado por seguridad.
safe_create_nsg_rule "$NSG_STORAGE" \
    -n DenyInternetToStorage \
    --priority 4000 \
    --direction Inbound \
    --access Deny \
    --protocol '*' \
    --source-address-prefixes Internet \
    --source-port-ranges '*' \
    --destination-address-prefixes 10.20.2.0/24 \
    --destination-port-ranges '*' \
    --description "Bloqueado por seguridad"

# DENEGAR: Origen: Storage -> Destino: Internet | Puerto: Todos | Justificación: Bloqueado por seguridad.
safe_create_nsg_rule "$NSG_STORAGE" \
    -n DenyStorageToInternet \
    --priority 4000 \
    --direction Outbound \
    --access Deny \
    --protocol '*' \
    --source-address-prefixes 10.20.2.0/24 \
    --source-port-ranges '*' \
    --destination-address-prefixes Internet \
    --destination-port-ranges '*' \
    --description "Bloqueado por seguridad"


# 3. Asignar Reglas al NSG de AppService (nsg-appservice)
echo "Asignando reglas a $NSG_APP..."

# PERMITIR: Origen: Management -> Destino: AppService | Puerto: 443 | Justificación: Administración.
safe_create_nsg_rule "$NSG_APP" \
    -n AllowManagementToAppService \
    --priority 100 \
    --direction Inbound \
    --access Allow \
    --protocol Tcp \
    --source-address-prefixes 10.20.5.0/24 \
    --source-port-ranges '*' \
    --destination-address-prefixes 10.20.1.0/24 \
    --destination-port-ranges 443 \
    --description "Administracion"

# (Opcional) Regla Outbound de AppService para habilitar la salida hacia Storage/Queue
safe_create_nsg_rule "$NSG_APP" \
    -n AllowAppServiceToStorageOutbound \
    --priority 100 \
    --direction Outbound \
    --access Allow \
    --protocol Tcp \
    --source-address-prefixes 10.20.1.0/24 \
    --source-port-ranges '*' \
    --destination-address-prefixes 10.20.2.0/24 \
    --destination-port-ranges 443 \
    --description "Permitir trafico de salida hacia Storage y Queue"

# DENEGAR: Todo el tráfico de VNet no autorizado por defecto
safe_create_nsg_rule "$NSG_APP" \
    -n DenyAllVnetInbound \
    --priority 4095 \
    --direction Inbound \
    --access Deny \
    --protocol '*' \
    --source-address-prefixes VirtualNetwork \
    --source-port-ranges '*' \
    --destination-address-prefixes '*' \
    --destination-port-ranges '*' \
    --description "Principio Menor Acceso - Bloquear trafico VNet no explicito"

safe_create_nsg_rule "$NSG_STORAGE" \
    -n DenyAllVnetInbound \
    --priority 4095 \
    --direction Inbound \
    --access Deny \
    --protocol '*' \
    --source-address-prefixes VirtualNetwork \
    --source-port-ranges '*' \
    --destination-address-prefixes '*' \
    --destination-port-ranges '*' \
    --description "Principio Menor Acceso - Bloquear trafico VNet no explicito"


# 4. Asociar los NSGs a sus respectivas Subnets
echo "Asociando NSGs a las Subnets correspondientes..."

az network vnet subnet update -g $RG_NAME --vnet-name $VNET_NAME \
    -n "$SNET_APP" \
    --network-security-group "$NSG_APP"

az network vnet subnet update -g $RG_NAME --vnet-name $VNET_NAME \
    -n "$SNET_STORAGE" \
    --network-security-group "$NSG_STORAGE"

az network vnet subnet update -g $RG_NAME --vnet-name $VNET_NAME \
    -n "$SNET_MGT" \
    --network-security-group "$NSG_MGT"

echo "Reglas NSG creadas y asignadas exitosamente."
