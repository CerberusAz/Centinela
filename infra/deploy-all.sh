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
export LOCATION="centralus"
export REGION_SHORT="cus"
export APP_SERVICE_SKU="B1" # Mantenemos B1

# Semana 2: Azure SQL requiere un admin AAD en la creación del servidor
# (azureADOnlyAuthentication=true, sin usuario/contraseña SQL). Se toma la
# identidad de quien tiene sesión activa en az cli -- normalmente quien
# ejecuta este script.
SQL_AAD_ADMIN_LOGIN=$(az ad signed-in-user show --query "userPrincipalName" -o tsv)
SQL_AAD_ADMIN_OBJECT_ID=$(az ad signed-in-user show --query "id" -o tsv)

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
      sqlAadAdminLogin="$SQL_AAD_ADMIN_LOGIN" \
      sqlAadAdminObjectId="$SQL_AAD_ADMIN_OBJECT_ID" \
  --output json)

echo "✔️  Infraestructura aprovisionada."
echo ""

# Extraer valores de salida de Bicep
RG_NAME=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.properties.outputs.resourceGroupName.value')
APP_SERVICE_NAME=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.properties.outputs.webAppName.value')
SCORING_FUNCTION_NAME=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.properties.outputs.scoringFunctionAppName.value')
CASES_FUNCTION_NAME=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.properties.outputs.casesFunctionAppName.value')
EXPLAINER_FUNCTION_NAME=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.properties.outputs.explainerFunctionAppName.value')
COSMOS_ACCOUNT_NAME=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.properties.outputs.cosmosAccountName.value')
SQL_SERVER_FQDN=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.properties.outputs.sqlServerFqdn.value')
ACR_LOGIN_SERVER=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.properties.outputs.acrLoginServer.value')
APP_INSIGHTS_NAME=$(echo "$DEPLOYMENT_OUTPUT" | jq -r '.properties.outputs.appInsightsName.value')

echo "[Paso 2 de 4] Desplegando código de la API al App Service ($APP_SERVICE_NAME)..."
API_DIR="$(cd "$SCRIPT_DIR/../api" &> /dev/null && pwd)"

if [ -d "$API_DIR" ]; then
    echo "Comprimiendo código en $API_DIR..."
    (cd "$API_DIR" && zip -r api.zip . -x ".*" -x "__pycache__/*" -x "venv/*" -x ".venv/*" > /dev/null)

    echo "Subiendo código comprimido a Azure..."
    az webapp deploy --resource-group "$RG_NAME" --name "$APP_SERVICE_NAME" --src-path "$API_DIR/api.zip" --type zip -o none

    echo "Limpiando archivo comprimido local..."
    rm -f "$API_DIR/api.zip"
    echo "✔️  ¡Despliegue de la API completado!"
else
    echo "⚠️  Advertencia: No se encontró el directorio de la API en $API_DIR. Omitiendo despliegue de código."
fi

deploy_function_code() {
    local component_dir="$1"
    local function_app_name="$2"
    local label="$3"

    if [ ! -d "$component_dir" ]; then
        echo "⚠️  Advertencia: No se encontró $component_dir. Omitiendo despliegue de $label."
        return
    fi

    echo "Comprimiendo código en $component_dir..."
    (cd "$component_dir" && zip -r "${label}.zip" . \
        -x ".*" -x "__pycache__/*" -x "venv/*" -x ".venv/*" -x "tests/*" -x "local.settings.json" \
        > /dev/null)

    echo "Subiendo código comprimido de $label a Azure ($function_app_name)..."
    az functionapp deployment source config-zip \
        --resource-group "$RG_NAME" \
        --name "$function_app_name" \
        --src "$component_dir/${label}.zip" \
        -o none

    echo "Limpiando archivo comprimido local..."
    rm -f "$component_dir/${label}.zip"
    echo "✔️  ¡Despliegue de $label completado!"
}

echo "[Paso 3 de 4] Desplegando el motor de scoring ($SCORING_FUNCTION_NAME)..."
deploy_function_code "$(cd "$SCRIPT_DIR/../scoring" &> /dev/null && pwd)" "$SCORING_FUNCTION_NAME" "scoring"

echo "Configurando suscripción de Event Grid hacia la Azure Function..."
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
az eventgrid event-subscription create \
  --name sub-scoring-function \
  --source-resource-id "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG_NAME/providers/Microsoft.EventGrid/topics/evt-$PROJECT_PREFIX-$ENVIRONMENT-$REGION_SHORT-$INSTANCE" \
  --endpoint-type azurefunction \
  --endpoint "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG_NAME/providers/Microsoft.Web/sites/$SCORING_FUNCTION_NAME/functions/ScoringFunction" \
  -o none

echo "[Paso 4 de 4] Desplegando la creación de casos ($CASES_FUNCTION_NAME)..."
deploy_function_code "$(cd "$SCRIPT_DIR/../cases" &> /dev/null && pwd)" "$CASES_FUNCTION_NAME" "cases"

echo "===================================================================="
echo "✅ DESPLIEGUE DE ARQUITECTURA FINALIZADO CON ÉXITO"
echo "===================================================================="
echo "⚠️  Pasos manuales pendientes:"
echo "    1. Ejecutar contra las bases '$CASES_FUNCTION_NAME' y '$EXPLAINER_FUNCTION_NAME' el CREATE USER ... FROM"
echo "       EXTERNAL PROVIDER documentado en docs/decisiones-arquitectura.md."
echo "    2. Aplicar el script de migración SQL del explicador:"
echo "       explainer/schema_patch.sql"
echo "===================================================================="
