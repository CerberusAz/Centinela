#!/usr/bin/env bash

# ==============================================================================
# teardown-all.sh
# Script para destruir TODA la infraestructura de Centinela automáticamente
# (Sin confirmaciones). Ideal para evitar cobros sorpresa al fin del día.
# ==============================================================================

set -euo pipefail

# Las mismas variables centrales
export PROJECT_PREFIX="trial"
export ENVIRONMENT="dev"
export INSTANCE="001"
export REGION_SHORT="eus2"

RESOURCE_GROUP="rg-${PROJECT_PREFIX}-${ENVIRONMENT}-${REGION_SHORT}-${INSTANCE}"

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
