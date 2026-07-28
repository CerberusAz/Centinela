#!/bin/bash

# 01-create-network.sh
# Script para generar la arquitectura de red base

# Variables
PROJECT_PREFIX="${PROJECT_PREFIX:-trial}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
INSTANCE="${INSTANCE:-001}"
REGION_SHORT="${REGION_SHORT:-eus2}"
LOCATION="${LOCATION:-eastus2}"

RG_NAME="rg-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}"
VNET_NAME="vnet-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}"
VNET_PREFIX="10.20.0.0/16"

SNET_APP="snet-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}-app"
SNET_STORAGE="snet-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}-st"
SNET_DB="snet-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}-db"
SNET_SCORING="snet-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}-scoring"
SNET_MGT="snet-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}-mgt"

if [ "$(az group exists -n $RG_NAME)" = "false" ]; then
    echo "Creando Grupo de Recursos: $RG_NAME en $LOCATION..."
    az group create --name $RG_NAME --location $LOCATION
else
    echo "El Grupo de Recursos '$RG_NAME' ya existe."
fi

if ! az network vnet show -g $RG_NAME -n $VNET_NAME > /dev/null 2>&1; then
    echo "Creando Virtual Network: $VNET_NAME ($VNET_PREFIX)..."
    az network vnet create \
        --resource-group $RG_NAME \
        --name $VNET_NAME \
        --address-prefix $VNET_PREFIX
else
    echo "La Virtual Network '$VNET_NAME' ya existe."
fi

safe_create_subnet() {
    local subnet_name=$1
    local address_prefix=$2
    local extra_args=$3
    if ! az network vnet subnet show -g $RG_NAME --vnet-name $VNET_NAME -n $subnet_name > /dev/null 2>&1; then
        echo "Creando Subnet: $subnet_name ($address_prefix)..."
        if [ -n "$extra_args" ]; then
            az network vnet subnet create --resource-group $RG_NAME --vnet-name $VNET_NAME --name $subnet_name --address-prefixes $address_prefix $extra_args
        else
            az network vnet subnet create --resource-group $RG_NAME --vnet-name $VNET_NAME --name $subnet_name --address-prefixes $address_prefix
        fi
    else
        echo "La Subnet '$subnet_name' ya existe."
    fi
}

safe_create_subnet "$SNET_APP" "10.20.1.0/24" "--delegations Microsoft.Web/serverFarms"
safe_create_subnet "$SNET_STORAGE" "10.20.2.0/24" ""
safe_create_subnet "$SNET_DB" "10.20.3.0/24" ""
safe_create_subnet "$SNET_SCORING" "10.20.4.0/24" ""
safe_create_subnet "$SNET_MGT" "10.20.5.0/24" ""

echo "Arquitectura de red creada exitosamente."
