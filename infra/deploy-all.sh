#!/usr/bin/env bash

# ==============================================================================
# deploy-all.sh (Bicep Version)
# Script maestro para el aprovisionamiento declarativo de Centinela
# ==============================================================================

set -euo pipefail

# 1. CONFIGURACIÓN CENTRAL
export ALERT_EMAIL="san.mu.zap@gmail.com"
export PROJECT_PREFIX="trial"
export ENVIRONMENT="dev"
export INSTANCE="003"
export LOCATION="westeurope"
export REGION_SHORT="weu"
export APP_SERVICE_SKU="B1" # B1 en westeurope para asegurar cuota activa y VNet Integration

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
BICEP_FILE="$SCRIPT_DIR/bicep/main.bicep"

echo "===================================================================="
echo "🚀 INICIANDO DESPLIEGUE DECLARATIVO DE ARQUITECTURA (BICEP)"
echo "===================================================================="
echo "Configuración activa:"
echo "  - Prefijo : $PROJECT_PREFIX"
echo "  - Entorno : $ENVIRONMENT-$INSTANCE"
echo "  - Región  : $LOCATION ($REGION_SHORT)"
echo "  - SKU App : $APP_SERVICE_SKU"
echo "===================================================================="
echo ""

echo "[Paso 1 de 2] Evaluando y Desplegando Infraestructura con Azure Bicep..."
# Ejecutamos el despliegue a nivel de suscripción
DEPLOYMENT_OUTPUT=$(az deployment sub create \
  --name "CentinelaDeploy-${INSTANCE}-${REGION_SHORT}" \
  --location "$LOCATION" \
  --template-file "$BICEP_FILE" \
  --parameters \
      prefix="$PROJECT_PREFIX" \
      env="$ENVIRONMENT" \
      instance="$INSTANCE" \
      regionShort="$REGION_SHORT" \
      location="$LOCATION" \
      alertEmail="$ALERT_EMAIL" \
      appServiceSku="$APP_SERVICE_SKU" \
  --output json)

echo "✔️  Infraestructura aprovisionada."
echo ""

# Extraer valores de salida de Bicep
RG_NAME=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.properties.outputs.resourceGroupName.value')
APP_NAME=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.properties.outputs.webAppName.value')

echo "[Paso 2 de 2] Desplegando código de la API al App Service ($APP_NAME)..."
API_DIR="$(cd "$SCRIPT_DIR/../api" &> /dev/null && pwd)"

if [ -d "$API_DIR" ]; then
    echo "Comprimiendo código en $API_DIR..."
    (cd "$API_DIR" && zip -r api.zip . -x ".*" -x "__pycache__/*" -x "venv/*" -x ".venv/*" > /dev/null)
    
    echo "Subiendo código comprimido a Azure..."
    az webapp deploy --resource-group "$RG_NAME" --name "$APP_NAME" --src-path "$API_DIR/api.zip" --type zip -o none
    
    echo "Limpiando archivo comprimido local..."
    rm -f "$API_DIR/api.zip"
    echo "✔️  ¡Despliegue de la API completado!"
else
    echo "⚠️  Advertencia: No se encontró el directorio de la API en $API_DIR. Omitiendo despliegue de código."
fi

echo "===================================================================="
echo "✅ DESPLIEGUE DE ARQUITECTURA FINALIZADO CON ÉXITO"
echo "===================================================================="
