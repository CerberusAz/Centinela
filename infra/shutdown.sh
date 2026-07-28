#!/usr/bin/env bash

set -euo pipefail

# --- CONFIGURACIÓN ---
PROJECT_PREFIX="${PROJECT_PREFIX:-trial}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
INSTANCE="${INSTANCE:-001}"
REGION_SHORT="${REGION_SHORT:-eus2}"

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}}"
APP_PLAN_NAME="${APP_PLAN_NAME:-plan-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}}"
WEB_APP_NAME="${WEB_APP_NAME:-app-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}}"
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-}"

# --- FUNCIONES AUXILIARES ---
log() {
  echo "$*"
}

warn() {
  echo "WARN: $*" >&2
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "El comando '$1' no está instalado."
}

ensure_login() {
  az account show >/dev/null 2>&1 || die "No hay sesión activa de Azure CLI. Ejecuta 'az login' primero."
}

ensure_subscription() {
  if [ -n "$SUBSCRIPTION_ID" ]; then
    az account set --subscription "$SUBSCRIPTION_ID" >/dev/null 2>&1 || die "No se pudo seleccionar la suscripción '$SUBSCRIPTION_ID'."
  fi
}

resource_exists() {
  local resource_type=${1:-}
  local name=${2:-}
  local rg=${3:-}

  case "$resource_type" in
    group)
      az group exists --name "$name" | grep -q true
      ;;
    plan)
      az appservice plan show --name "$name" --resource-group "$rg" -o none 2>/dev/null
      ;;
    webapp)
      az webapp show --name "$name" --resource-group "$rg" -o none 2>/dev/null
      ;;
    *)
      return 1
      ;;
  esac
}

normalize_region_short() {
  case "${REGION_SHORT,,}" in
    eastus2|eastus|eus2|eus|e)
      REGION_SHORT="eus2"
      ;;
    westus2|westus|wus2|wus|w)
      REGION_SHORT="wus2"
      ;;
    *)
      REGION_SHORT="${REGION_SHORT:-wus2}"
      ;;
  esac
}

find_resource_group() {
  if [ -n "$RESOURCE_GROUP" ] && resource_exists group "$RESOURCE_GROUP"; then
    echo "$RESOURCE_GROUP"
    return 0
  fi

  local matching_rg=""
  matching_rg=$(az group list --query "[?starts_with(name, 'rg-${PROJECT_PREFIX}-${ENVIRONMENT}-')].name" -o tsv 2>/dev/null | grep -E "-${REGION_SHORT}-" | head -n 1 || true)
  if [ -n "$matching_rg" ]; then
    echo "$matching_rg"
    return 0
  fi

  matching_rg=$(az group list --query "[?starts_with(name, 'rg-${PROJECT_PREFIX}-${ENVIRONMENT}-')].name" -o tsv 2>/dev/null | head -n 1 || true)
  if [ -n "$matching_rg" ]; then
    echo "$matching_rg"
    return 0
  fi

  az webapp list --query "[?contains(name, '${PROJECT_PREFIX}-${ENVIRONMENT}')].resourceGroup" -o tsv 2>/dev/null | head -n 1 || true
}

find_app_service_plan() {
  local rg=$1
  if [ -n "$rg" ]; then
    az appservice plan list --resource-group "$rg" --query "[?contains(name, '${PROJECT_PREFIX}-${ENVIRONMENT}') || contains(name, '${PROJECT_PREFIX}')].name" -o tsv 2>/dev/null | head -n 1 || true
  else
    az appservice plan list --query "[?contains(name, '${PROJECT_PREFIX}-${ENVIRONMENT}') || contains(name, '${PROJECT_PREFIX}')].name" -o tsv 2>/dev/null | head -n 1 || true
  fi
}

find_web_app() {
  local rg=$1
  if [ -n "$rg" ]; then
    az webapp list --resource-group "$rg" --query "[?contains(name, '${PROJECT_PREFIX}-${ENVIRONMENT}') || contains(name, '${PROJECT_PREFIX}')].name" -o tsv 2>/dev/null | head -n 1 || true
  else
    az webapp list --query "[?contains(name, '${PROJECT_PREFIX}-${ENVIRONMENT}') || contains(name, '${PROJECT_PREFIX}')].name" -o tsv 2>/dev/null | head -n 1 || true
  fi
}

resolve_resources() {
  local detected_rg=""
  local detected_plan=""
  local detected_webapp=""

  normalize_region_short
  detected_rg=$(find_resource_group || true)
  if [ -n "$detected_rg" ]; then
    RESOURCE_GROUP="$detected_rg"
  else
    RESOURCE_GROUP="${RESOURCE_GROUP:-rg-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}}"
  fi

  if resource_exists group "$RESOURCE_GROUP"; then
    detected_plan=$(find_app_service_plan "$RESOURCE_GROUP" || true)
    detected_webapp=$(find_web_app "$RESOURCE_GROUP" || true)
  fi

  if [ -z "$detected_plan" ]; then
    detected_plan=$(find_app_service_plan "" || true)
  fi

  if [ -z "$detected_webapp" ]; then
    detected_webapp=$(find_web_app "" || true)
  fi

  if [ -n "$detected_plan" ]; then
    APP_PLAN_NAME="$detected_plan"
  else
    APP_PLAN_NAME="plan-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}"
  fi

  if [ -n "$detected_webapp" ]; then
    WEB_APP_NAME="$detected_webapp"
  else
    WEB_APP_NAME="app-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}"
  fi
}

stop_web_app() {
  if ! resource_exists webapp "$WEB_APP_NAME" "$RESOURCE_GROUP"; then
    die "El Web App '$WEB_APP_NAME' no existe en el Resource Group '$RESOURCE_GROUP'."
  fi

  log "Deteniendo la Web App '$WEB_APP_NAME'..."
  az webapp stop --name "$WEB_APP_NAME" --resource-group "$RESOURCE_GROUP" -o none
  log "Web App detenida correctamente."
}

scale_to_free() {
  if ! resource_exists group "$RESOURCE_GROUP"; then
    die "El Resource Group '$RESOURCE_GROUP' no existe."
  fi

  if ! resource_exists plan "$APP_PLAN_NAME" "$RESOURCE_GROUP"; then
    die "El App Service Plan '$APP_PLAN_NAME' no existe en '$RESOURCE_GROUP'."
  fi

  if ! resource_exists webapp "$WEB_APP_NAME" "$RESOURCE_GROUP"; then
    die "El Web App '$WEB_APP_NAME' no existe en '$RESOURCE_GROUP'."
  fi

  log "1. Deteniendo la Web App '$WEB_APP_NAME'..."
  az webapp stop --name "$WEB_APP_NAME" --resource-group "$RESOURCE_GROUP" -o none

  log "2. Escalando el App Service Plan '$APP_PLAN_NAME' al SKU Gratuito (F1)..."
  az appservice plan update --name "$APP_PLAN_NAME" --resource-group "$RESOURCE_GROUP" --sku F1 -o none

  log "Operación completada. La aplicación está detenida y el plan quedó en F1."
}

delete_resource_group() {
  if ! resource_exists group "$RESOURCE_GROUP"; then
    warn "El Resource Group '$RESOURCE_GROUP' no existe. No hay nada que eliminar."
    exit 0
  fi

  read -rp "¿Estás seguro de que deseas ELIMINAR COMPLETAMENTE el Grupo de Recursos '$RESOURCE_GROUP'? (s/n): " CONFIRM
  case "${CONFIRM,,}" in
    s|si|yes|y)
      log "Eliminando el Grupo de Recursos '$RESOURCE_GROUP'..."
      az group delete --name "$RESOURCE_GROUP" --yes --no-wait -o none
      log "La eliminación se ha iniciado en Azure."
      ;;
    *)
      log "Operación cancelada."
      ;;
  esac
}

# --- VALIDACIONES INICIALES ---
require_command az
require_command jq
ensure_login
ensure_subscription

SUBSCRIPTION_NAME=$(az account show --query name -o tsv)
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

resolve_resources

if [ -z "$RESOURCE_GROUP" ] || [ -z "$APP_PLAN_NAME" ] || [ -z "$WEB_APP_NAME" ]; then
  die "Los nombres de recurso no pueden quedar vacíos. Revisa la configuración del script."
fi

log "=============================================================================="
log "Menú de Control de Costos para Azure App Service"
log "=============================================================================="
log "Suscripción activa: ${SUBSCRIPTION_NAME} (${SUBSCRIPTION_ID})"
log "Resource Group     : ${RESOURCE_GROUP}"
log "App Service Plan   : ${APP_PLAN_NAME}"
log "Web App            : ${WEB_APP_NAME}"
log "=============================================================================="
log "1) Apagar la Web App solamente"
log "2) Escalar a Capa Gratuita (F1) y detener la Web App"
log "3) Eliminar todo el Grupo de Recursos"
log "4) Salir"
log "=============================================================================="
read -rp "Selecciona una opción (1-4): " OPTION

case "$OPTION" in
  1)
    stop_web_app
    ;;
  2)
    scale_to_free
    ;;
  3)
    delete_resource_group
    ;;
  4)
    log "Saliendo del script."
    exit 0
    ;;
  *)
    die "Opción no válida."
    ;;
esac
