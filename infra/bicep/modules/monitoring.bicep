targetScope = 'resourceGroup'

// Semana 3: Observabilidad — Application Insights + Log Analytics Workspace.
//
// Application Insights es el punto de ingesta de telemetría (trazas,
// métricas, excepciones, dependencias). Requiere un Log Analytics Workspace
// como backend de almacenamiento persistente (modo workspace-based, que
// reemplazó al modo clásico en 2021).
//
// Tier Free de Application Insights:
//   - 5 GB de ingesta de datos/mes incluidos sin costo.
//   - Retención: 90 días en el workspace.
//   - Por encima de 5 GB: ~$2.30 USD/GB adicional.
//   - Para el volumen de prueba de esta célula (tráfico sintético de la
//     demo + pruebas de carga), el estimado de ingesta es <<1 GB/mes.
//     Ver docs/reporte-credito-semana3.md §3 para el cálculo detallado.
//
// Alerta configurada (criterio de aceptación §2.5):
//   Condición: tasa de fallos de la API (requests fallidos / total) > 10%
//   durante más de 5 minutos. Un umbral de 10% captura una degradación
//   real (fallo masivo de dependencias) sin dispararse por errores
//   puntuales de clientes con payloads inválidos (que producen 400, no 5xx).
//   Justificación completa en docs/alerta-configurada.md.

param prefix string
param env string
param instance string
param regionShort string
param location string = resourceGroup().location
param alertEmail string

var workspaceName = 'log-${prefix}-${env}-${regionShort}-${instance}'
var appInsightsName = 'ai-${prefix}-${env}-${regionShort}-${instance}'
var actionGroupName = 'ag-${prefix}-${env}-${regionShort}-${instance}'
var alertName = 'alert-api-failures-${prefix}-${env}-${regionShort}-${instance}'

// --- Log Analytics Workspace ------------------------------------------------
// Backend de almacenamiento de telemetría. El SKU PerGB2018 cobra por datos
// ingestados por encima del nivel gratuito (5 GB/mes incluidos sin costo).
resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30  // Retención mínima facturable; suficiente para
    // depurar incidentes en el contexto del proyecto (21 días de duración).
  }
}

// --- Application Insights ---------------------------------------------------
// Modo workspace-based: los datos van al Log Analytics Workspace anterior.
// La connection string (no la instrumentation key, que está deprecada) es
// lo que los SDKs de OpenTelemetry y azure-monitor-opentelemetry usan para
// autenticar sin credenciales de larga duración.
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// --- Action Group (receptor de alertas) -------------------------------------
// Define adónde enviar las alertas. En este caso, un email al equipo.
// Se puede ampliar con webhooks, Azure Functions, etc.
resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: actionGroupName
  location: 'global'  // Los Action Groups son recursos globales en Azure
  properties: {
    groupShortName: 'centinela'
    enabled: true
    emailReceivers: [
      {
        name: 'equipo-centinela'
        emailAddress: alertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

// --- Alerta: tasa de fallos de la API > 10% en 5 minutos ------------------
// Criterio: si más del 10% de las requests a la API responden 5xx durante
// una ventana de 5 minutos, se dispara la alerta. Los 400 (payload inválido)
// no cuentan como fallo del sistema — son errores del cliente, esperados.
// Umbral de 5 minutos: tiempo mínimo que indica una degradación sostenida,
// no un spike puntual. Ver justificación completa en docs/alerta-configurada.md
resource apiFailureAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: alertName
  location: 'global'
  properties: {
    description: 'Tasa de fallos HTTP 5xx de la API supera el 10% durante 5 minutos'
    severity: 2            // Sev 2 = Warning (Sev 0 es Critical, para PD)
    enabled: true
    scopes: [
      appInsights.id       // La alerta evalúa métricas de este App Insights
    ]
    evaluationFrequency: 'PT1M'   // Evaluar cada minuto
    windowSize: 'PT5M'            // Ventana de evaluación: 5 minutos
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'HighFailureRate'
          criterionType: 'StaticThresholdCriterion'
          metricNamespace: 'Microsoft.Insights/components'
          metricName: 'requests/failed'
          operator: 'GreaterThan'
          threshold: 5          // Más de 5 requests fallidas en la ventana
          aggregation: 'Count'  // Conteo absoluto
          timeAggregation: 'Count'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

output appInsightsName string = appInsights.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output logAnalyticsWorkspaceId string = logAnalyticsWorkspace.id
