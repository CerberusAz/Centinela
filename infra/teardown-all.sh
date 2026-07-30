#!/usr/bin/env bash

# ==============================================================================
# teardown-all.sh
# Script para destruir TODA la infraestructura de Centinela automáticamente
# (Sin confirmaciones). Ideal para evitar cobros sorpresa al fin del día.
# ==============================================================================

set -euo pipefail

# Las mismas variables centrales que deploy-all.sh. Se pueden sobreescribir
# por entorno (p. ej. RESOURCE_GROUP=rg-trial-dev-weu-004 ./teardown-all.sh)
# para no depender de que PROJECT_PREFIX/ENVIRONMENT/INSTANCE/REGION_SHORT
# se mantengan sincronizados a mano con lo que realmente desplegó
# deploy-all.sh.
PROJECT_PREFIX="${PROJECT_PREFIX:-trial}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
INSTANCE="${INSTANCE:-003}"
REGION_SHORT="${REGION_SHORT:-weu}"
RESOURCE_GROUP="${RESOURCE_GROUP:-}"

# Si no se pasó RESOURCE_GROUP explícito, intentar autodetectar el grupo
# real en la suscripción en vez de asumir que INSTANCE/REGION_SHORT de
# arriba siguen coincidiendo con el último despliegue (la causa de que
# este script apuntara antes a un grupo que ya no existía).
if [ -z "$RESOURCE_GROUP" ]; then
    CANDIDATE=$(az group list \
        --query "[?starts_with(name, 'rg-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-')].name" \
        -o tsv 2>/dev/null | head -n 1 || true)

    if [ -z "$CANDIDATE" ]; then
        CANDIDATE=$(az group list \
            --query "[?starts_with(name, 'rg-${PROJECT_PREFIX}-${ENVIRONMENT}-')].name" \
            -o tsv 2>/dev/null | head -n 1 || true)
    fi

    RESOURCE_GROUP="${CANDIDATE:-rg-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}}"
fi

echo "===================================================================="
echo "⚠️  INICIANDO DESTRUCCIÓN TOTAL DE LA ARQUITECTURA CENTINELA"
echo "===================================================================="
echo "Grupo de Recursos Objetivo: $RESOURCE_GROUP"

if az group exists --name "$RESOURCE_GROUP" | grep -q true; then
    echo "Destruyendo el grupo de recursos y TODO su contenido de fondo..."
    az group delete --name "$RESOURCE_GROUP" --yes --no-wait
    echo "✔️  Comando de eliminación enviado."
    echo "Azure está borrando los recursos en segundo plano. Ya no generarán costos."
else
    echo "✔️  El grupo de recursos '$RESOURCE_GROUP' no existe. No hay nada que borrar."
fi
echo "===================================================================="
