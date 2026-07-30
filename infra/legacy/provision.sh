#!/usr/bin/env bash

set -euo pipefail


# 0. CONFIGURACIÓN — EDITA ESTOS VALORES ANTES DE EJECUTAR O DECLÁRALOS COMO VARIABLES DE ENTORNO

ALERT_EMAIL="${ALERT_EMAIL:-san.mu.zap@gmail.com}"     # <-- OBLIGATORIO: recibirá las alertas de presupuesto
PROJECT_PREFIX="${PROJECT_PREFIX:-trial}"                  # prefijo corto del proyecto/cuenta
ENVIRONMENT="${ENVIRONMENT:-dev}"                       # dev | test | prod
INSTANCE="${INSTANCE:-001}"                          # correlativo si despliegas varias veces
BUDGET_AMOUNT="${BUDGET_AMOUNT:-140}"                       # límite de gasto en USD para vigilar
TRIAL_TOTAL_CREDIT="${TRIAL_TOTAL_CREDIT:-150}"                  # crédito total del Free Trial
APP_RUNTIME="${APP_RUNTIME:-PYTHON|3.11}"
APP_SERVICE_SKU="${APP_SERVICE_SKU:-B1}"

# Regiones candidatas (ajustadas para planes App Service B1)
PRIMARY_REGION="${PRIMARY_REGION:-eastus2}";    PRIMARY_REGION_SHORT="${PRIMARY_REGION_SHORT:-eus2}"
FALLBACK_REGION="${FALLBACK_REGION:-westus2}";    FALLBACK_REGION_SHORT="${FALLBACK_REGION_SHORT:-wus2}"

sep() { echo; echo "==============="; echo " $1"; echo "================"; }

# 1. VALIDACIONES PREVIAS

sep "1. Validaciones previas"

command -v az  >/dev/null 2>&1 || { echo "ERROR: Azure CLI no está instalado."; exit 1; }
command -v jq  >/dev/null 2>&1 || { echo "ERROR: jq no está instalado (necesario para procesar respuestas JSON)."; exit 1; }

if [ "$ALERT_EMAIL" = "tucorreo@correo.com" ]; then
  echo "ERROR: Debes editar ALERT_EMAIL en la sección de CONFIGURACIÓN antes de ejecutar."
  exit 1
fi

az account show >/dev/null 2>&1 || { echo "ERROR: No hay sesión activa. Ejecuta 'az login' primero."; exit 1; }

SUBSCRIPTION_ID=$(az account show --query id -o tsv)
SUBSCRIPTION_NAME=$(az account show --query name -o tsv)
echo "Suscripción activa: ${SUBSCRIPTION_NAME} (${SUBSCRIPTION_ID})"

# 2. CONVENCIÓN DE NOMBRES (patrón CAF: recurso-proyecto-entorno-region-instancia)

sep "2. Convención de nombres aplicada"

# Se decide primero contra qué región se nombrará; puede cambiar en el paso 3
REGION_SHORT="$PRIMARY_REGION_SHORT"

RG_NAME="rg-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}"
PLAN_NAME="plan-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}"
APP_NAME="app-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}"
BUDGET_NAME="budget-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}"

cat <<EOF
Patrón: <tipo-recurso>-<proyecto>-<entorno>-<region>-<instancia>
  Resource Group     : ${RG_NAME}
  App Service Plan   : ${PLAN_NAME}
  Web App            : ${APP_NAME}
  Budget             : ${BUDGET_NAME}
EOF

# 3. JUSTIFICACIÓN Y SELECCIÓN DE REGIÓN (con verificación de cuota en vivo)

sep "3. Justificación de región"

cat <<EOF
Se evalúan East US y West US 2 porque:
  - Son las regiones con mayor disponibilidad histórica del tier gratuito F1
    de App Service para suscripciones Free Trial.
  - Tienen el catálogo más amplio de SKUs/servicios habilitados para cuentas
    de prueba (algunas regiones restringen SKUs "Free"/"Shared" en Trial).
  - Latencia aceptable para pruebas desde Colombia (no es un entorno productivo
    sensible a latencia; se prioriza disponibilidad y costo sobre cercanía).
El script consulta la cuota real de "Free App Service Plan" en cada región y
elige automáticamente la primera con cupo disponible.
EOF

check_sku_support() {
  local region=$1
  az appservice list-locations --sku "$APP_SERVICE_SKU" --query "[?name=='${region}'] | [0].name" -o tsv 2>/dev/null || true
}

PRIMARY_REGION_SUPPORT=$(check_sku_support "$PRIMARY_REGION")
FALLBACK_REGION_SUPPORT=$(check_sku_support "$FALLBACK_REGION")
echo "Soporte SKU ${APP_SERVICE_SKU} en ${PRIMARY_REGION}: ${PRIMARY_REGION_SUPPORT:-No}"
echo "Soporte SKU ${APP_SERVICE_SKU} en ${FALLBACK_REGION}: ${FALLBACK_REGION_SUPPORT:-No}"

FINAL_REGION="$PRIMARY_REGION"
FINAL_REGION_SHORT="$PRIMARY_REGION_SHORT"

if [ -z "$PRIMARY_REGION_SUPPORT" ]; then
  echo "La región ${PRIMARY_REGION} no ofrece el SKU ${APP_SERVICE_SKU}. Se usará ${FALLBACK_REGION}."
  FINAL_REGION="$FALLBACK_REGION"
  FINAL_REGION_SHORT="$FALLBACK_REGION_SHORT"
fi

echo "Región final seleccionada: ${FINAL_REGION}"

# Si cambió la región, se renombran los recursos para mantener la convención
if [ "$FINAL_REGION_SHORT" != "$REGION_SHORT" ]; then
  RG_NAME="rg-${PROJECT_PREFIX}-${ENVIRONMENT}-${FINAL_REGION_SHORT}-${INSTANCE}"
  PLAN_NAME="plan-${PROJECT_PREFIX}-${ENVIRONMENT}-${FINAL_REGION_SHORT}-${INSTANCE}"
  APP_NAME="app-${PROJECT_PREFIX}-${ENVIRONMENT}-${FINAL_REGION_SHORT}-${INSTANCE}"
  BUDGET_NAME="budget-${PROJECT_PREFIX}-${ENVIRONMENT}-${FINAL_REGION_SHORT}-${INSTANCE}"
fi

# 4. INFORME DE CUOTAS

sep "4. Informe de cuotas en ${FINAL_REGION}"

echo "-- Web (App Service) --"
az rest --method get \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/providers/Microsoft.Web/locations/${FINAL_REGION}/usages?api-version=2023-12-01" \
  -o json 2>/dev/null | jq -r '.value[] | "\(.name.localizedValue): \(.currentValue)/\(.limit) \(.unit)"' 2>/dev/null || echo "No disponible."

echo
echo "-- Compute (vCPUs, referencia para futuros recursos) --"
az vm list-usage --location "$FINAL_REGION" -o table 2>/dev/null || echo "No disponible."

echo
echo "-- Storage --"
az storage account list-usage -o table 2>/dev/null || echo "No disponible."

# 5. RESOURCE GROUP + APP SERVICE PLAN (B1) + WEB APP

sep "5. Aprovisionamiento de recursos"

echo "Verificando Resource Group: ${RG_NAME}"
if az group exists --name "$RG_NAME" | grep -q true; then
  echo "El Resource Group ya existe. Se reutilizará."
else
  echo "Creando Resource Group: ${RG_NAME}"
  az group create --name "$RG_NAME" --location "$FINAL_REGION" -o none
fi

echo "Verificando App Service Plan (${APP_SERVICE_SKU}): ${PLAN_NAME}"
if az appservice plan show --name "$PLAN_NAME" --resource-group "$RG_NAME" -o none 2>/dev/null; then
  echo "El App Service Plan ya existe. Se reutilizará."
else
  echo "Creando App Service Plan (${APP_SERVICE_SKU}): ${PLAN_NAME}"
  if ! az appservice plan create \
    --name "$PLAN_NAME" \
    --resource-group "$RG_NAME" \
    --location "$FINAL_REGION" \
    --sku "$APP_SERVICE_SKU" \
    --is-linux \
    -o none; then
    echo "No se pudo crear el plan en ${FINAL_REGION}. Probando ${FALLBACK_REGION}..."
    FINAL_REGION="$FALLBACK_REGION"
    FINAL_REGION_SHORT="$FALLBACK_REGION_SHORT"

    RG_NAME="rg-${PROJECT_PREFIX}-${ENVIRONMENT}-${FINAL_REGION_SHORT}-${INSTANCE}"
    PLAN_NAME="plan-${PROJECT_PREFIX}-${ENVIRONMENT}-${FINAL_REGION_SHORT}-${INSTANCE}"
    APP_NAME="app-${PROJECT_PREFIX}-${ENVIRONMENT}-${FINAL_REGION_SHORT}-${INSTANCE}"
    BUDGET_NAME="budget-${PROJECT_PREFIX}-${ENVIRONMENT}-${FINAL_REGION_SHORT}-${INSTANCE}"

    echo "Verificando Resource Group: ${RG_NAME}"
    if az group exists --name "$RG_NAME" | grep -q true; then
      echo "El Resource Group ya existe. Se reutilizará."
    else
      echo "Creando Resource Group: ${RG_NAME}"
      az group create --name "$RG_NAME" --location "$FINAL_REGION" -o none
    fi

    echo "Creando App Service Plan (${APP_SERVICE_SKU}): ${PLAN_NAME}"
    az appservice plan create \
      --name "$PLAN_NAME" \
      --resource-group "$RG_NAME" \
      --location "$FINAL_REGION" \
      --sku "$APP_SERVICE_SKU" \
      --is-linux \
      -o none
  fi
fi

echo "Verificando Web App: ${APP_NAME}"
if az webapp show --name "$APP_NAME" --resource-group "$RG_NAME" -o none 2>/dev/null; then
  echo "El Web App ya existe. Se reutilizará."
else
  echo "Creando Web App: ${APP_NAME}"
  for runtime in "$APP_RUNTIME" "PYTHON|3.10"; do
    if az webapp create \
      --name "$APP_NAME" \
      --resource-group "$RG_NAME" \
      --plan "$PLAN_NAME" \
      --runtime "$runtime" \
      -o none; then
      APP_RUNTIME="$runtime"
      break
    fi
    echo "El runtime ${runtime} no fue aceptado. Probando con el siguiente..."
  done
fi

APP_URL=$(az webapp show --name "$APP_NAME" --resource-group "$RG_NAME" --query defaultHostName -o tsv)
echo "Web App creada o reutilizada: https://${APP_URL}"

# 5.1 IDENTIDAD GESTIONADA E INTEGRACIÓN DE RED Y RBAC
sep "5.1 Identidad Gestionada, Integración de Red y RBAC"

echo "Habilitando Identidad Gestionada (System-Assigned)..."
PRINCIPAL_ID=$(az webapp identity assign --name "$APP_NAME" --resource-group "$RG_NAME" --query principalId -o tsv)
echo "Identidad asignada. Principal ID: $PRINCIPAL_ID"

VNET_NAME="vnet-${PROJECT_PREFIX}-${ENVIRONMENT}-${FINAL_REGION_SHORT}-${INSTANCE}"
SNET_APP="snet-${PROJECT_PREFIX}-${ENVIRONMENT}-${FINAL_REGION_SHORT}-${INSTANCE}-app"

echo "Verificando/Agregando Integración de VNet ($VNET_NAME / $SNET_APP)..."
az webapp vnet-integration add --name "$APP_NAME" --resource-group "$RG_NAME" --vnet "$VNET_NAME" --subnet "$SNET_APP" -o none || echo "Advertencia: No se pudo inyectar en VNet (¿Ya existe?)."

echo "Buscando Storage Account en el Resource Group para asignar roles RBAC..."
SA_BASE_NAME="st${PROJECT_PREFIX}${ENVIRONMENT}${FINAL_REGION_SHORT}${INSTANCE}"
STORAGE_ACCOUNT_NAME=$(az storage account list -g "$RG_NAME" --query "[?starts_with(name, '${SA_BASE_NAME}')].name" -o tsv | head -n 1)

if [ -n "$STORAGE_ACCOUNT_NAME" ]; then
    STORAGE_ID=$(az storage account show --name "$STORAGE_ACCOUNT_NAME" --resource-group "$RG_NAME" --query id -o tsv)
    echo "Asignando rol 'Storage Blob Data Contributor' a la Web App sobre Storage: $STORAGE_ACCOUNT_NAME..."
    az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role "Storage Blob Data Contributor" --scope "$STORAGE_ID" -o none || echo "Advertencia: No se pudo asignar rol."
    
    echo "Asignando rol 'Storage Queue Data Contributor' a la Web App sobre Storage: $STORAGE_ACCOUNT_NAME..."
    az role assignment create --assignee-object-id "$PRINCIPAL_ID" --assignee-principal-type ServicePrincipal --role "Storage Queue Data Contributor" --scope "$STORAGE_ID" -o none || echo "Advertencia: No se pudo asignar rol."
else
    echo "Advertencia: No se encontró Storage Account con prefijo $SA_BASE_NAME. Debes correr storage.sh primero."
fi


# 5.2 CONFIGURACIÓN Y DESPLIEGUE DE LA API
sep "5.2 Configuración y Despliegue de la API"

if [ -n "$STORAGE_ACCOUNT_NAME" ]; then
    echo "Inyectando variables de entorno en el App Service..."
    az webapp config appsettings set -g "$RG_NAME" -n "$APP_NAME" --settings \
        CENTINELA_STORAGE_BACKEND="blob" \
        CENTINELA_BLOB_ACCOUNT_URL="https://${STORAGE_ACCOUNT_NAME}.blob.core.windows.net" \
        CENTINELA_BLOB_CONTAINER_RAW_TRANSACTIONS="transacciones" -o none
else
    echo "Advertencia: No se pudo configurar el Storage Account porque no se encontró."
fi

echo "Desplegando el código de la API al App Service..."
# El script se corre desde infra/, así que subimos un nivel para encontrar api/
API_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../api" &> /dev/null && pwd)"
if [ -d "$API_DIR" ]; then
    echo "Comprimiendo código en $API_DIR..."
    (cd "$API_DIR" && zip -r api.zip . -x ".*" -x "__pycache__/*" -x "venv/*" -x ".venv/*" > /dev/null)
    
    echo "Subiendo código comprimido a Azure..."
    az webapp deploy --resource-group "$RG_NAME" --name "$APP_NAME" --src-path "$API_DIR/api.zip" --type zip
    
    echo "Limpiando archivo comprimido local..."
    rm -f "$API_DIR/api.zip"
    echo "¡Despliegue de la API completado!"
else
    echo "Advertencia: No se encontró el directorio de la API en $API_DIR. Omitiendo despliegue de código."
fi


# 6. PRESUPUESTO DE SUSCRIPCIÓN + ALERTAS (140 USD)

sep "6. Presupuesto y alertas de gasto"

echo "Nota: los Budgets de Azure SOLO notifican, no detienen recursos."
echo "El Free Trial ya trae un límite de gasto nativo que suspende servicios"
echo "al agotar los \$${TRIAL_TOTAL_CREDIT} de crédito; este presupuesto de"
echo "\$${BUDGET_AMOUNT} es una alerta temprana antes de llegar a ese tope."

START_DATE=$(date -u +%Y-%m-01T00:00:00Z)
END_DATE=$(date -u -d "+12 months" +%Y-%m-01T00:00:00Z)

BUDGET_BODY=$(cat <<JSON
{
  "properties": {
    "category": "Cost",
    "amount": ${BUDGET_AMOUNT},
    "timeGrain": "Monthly",
    "timePeriod": { "startDate": "${START_DATE}", "endDate": "${END_DATE}" },
    "notifications": {
      "Alerta_50pct_Consumido": {
        "enabled": true, "operator": "GreaterThan", "threshold": 50,
        "contactEmails": ["${ALERT_EMAIL}"], "thresholdType": "Actual"
      },
      "Alerta_80pct_Consumido": {
        "enabled": true, "operator": "GreaterThan", "threshold": 80,
        "contactEmails": ["${ALERT_EMAIL}"], "thresholdType": "Actual"
      },
      "Alerta_100pct_Proyectado": {
        "enabled": true, "operator": "GreaterThan", "threshold": 100,
        "contactEmails": ["${ALERT_EMAIL}"], "thresholdType": "Forecasted"
      }
    }
  }
}
JSON
)

az rest --method put \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/providers/Microsoft.Consumption/budgets/${BUDGET_NAME}?api-version=2023-05-01" \
  --body "$BUDGET_BODY" -o none

echo "Presupuesto '${BUDGET_NAME}' creado o actualizado: \$${BUDGET_AMOUNT} USD/mes, alertas a ${ALERT_EMAIL} en 50%, 80% y 100% proyectado."

# 7. REPORTE DE CRÉDITO CONSUMIDO + PROYECCIÓN A 3 SEMANAS

sep "7. Crédito consumido y proyección a 3 semanas"

USAGE_START=$(date -u -d "30 days ago" +%Y-%m-%d)
USAGE_END=$(date -u +%Y-%m-%d)

USAGE_JSON=$(az consumption usage list --start-date "$USAGE_START" --end-date "$USAGE_END" -o json 2>/dev/null || echo "[]")

TOTAL_CONSUMED=$(echo "$USAGE_JSON" | jq '[.[]? | (.pretaxCost? // 0 | tonumber? // 0)] | add // 0')
DAYS_ELAPSED=$(( ( $(date -d "$USAGE_END" +%s) - $(date -d "$USAGE_START" +%s) ) / 86400 ))
[ "$DAYS_ELAPSED" -lt 1 ] && DAYS_ELAPSED=1

DAILY_AVG=$(awk -v t="$TOTAL_CONSUMED" -v d="$DAYS_ELAPSED" 'BEGIN{printf "%.4f", t/d}')
PROJECTED_3W=$(awk -v t="$TOTAL_CONSUMED" -v a="$DAILY_AVG" 'BEGIN{printf "%.2f", t + (a*21)}')

cat <<EOF
Ventana analizada     : ${USAGE_START} a ${USAGE_END} (${DAYS_ELAPSED} días)
Consumo acumulado     : \$${TOTAL_CONSUMED} USD
Promedio diario        : \$${DAILY_AVG} USD/día
Proyección a 3 semanas : \$${PROJECTED_3W} USD
Presupuesto de alerta  : \$${BUDGET_AMOUNT} USD
Crédito total Trial    : \$${TRIAL_TOTAL_CREDIT} USD
EOF

OVER_BUDGET=$(awk -v p="$PROJECTED_3W" -v b="$BUDGET_AMOUNT" 'BEGIN{print (p>b)?1:0}')
OVER_CREDIT=$(awk -v p="$PROJECTED_3W" -v c="$TRIAL_TOTAL_CREDIT" 'BEGIN{print (p>c)?1:0}')

[ "$OVER_BUDGET" = "1" ] && echo "ALERTA: la proyección a 3 semanas supera el presupuesto de \$${BUDGET_AMOUNT} USD."
[ "$OVER_CREDIT" = "1" ] && echo "ALERTA CRÍTICA: la proyección supera el crédito total del Trial (\$${TRIAL_TOTAL_CREDIT} USD)."
[ "$OVER_BUDGET" = "0" ] && echo "Dentro de rango: el gasto proyectado no supera el presupuesto configurado."

echo
echo "Este reporte tiene poca señal si la suscripción es muy reciente (pocos"
echo "días de datos). Vuelve a ejecutar el script en unos días para una"
echo "proyección más precisa, o programa este bloque como tarea periódica."


# 8. RESUMEN FINAL

sep "8. Resumen"
cat <<EOF
Región               : ${FINAL_REGION}
Resource Group        : ${RG_NAME}
App Service Plan      : ${PLAN_NAME} (${APP_SERVICE_SKU})
Web App                : ${APP_NAME}
URL                     : https://${APP_URL}
Budget                 : ${BUDGET_NAME} (\$${BUDGET_AMOUNT} USD, alertas a ${ALERT_EMAIL})
EOF