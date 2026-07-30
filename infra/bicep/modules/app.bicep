targetScope = 'resourceGroup'

param prefix string
param env string
param instance string
param regionShort string
param location string = resourceGroup().location
param subnetAppId string
param storageAccountBlobEndpoint string
param appServiceSku string = 'B1' // Requiere B1 mínimo para VNet Integration
param cosmosAccountUrl string
param eventGridTopicEndpoint string

var planName = 'plan-${prefix}-${env}-${regionShort}-${instance}'
var appName = 'app-${prefix}-${env}-${regionShort}-${instance}'

resource appServicePlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: planName
  location: location
  sku: {
    name: appServiceSku
  }
  properties: {
    reserved: true // Requerido para Linux
  }
  kind: 'linux'
}

resource webApp 'Microsoft.Web/sites@2022-09-01' = {
  name: appName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    virtualNetworkSubnetId: (appServiceSku != 'F1' && appServiceSku != 'D1') ? subnetAppId : null
    siteConfig: {
      appCommandLine: 'gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app'
      linuxFxVersion: 'PYTHON|3.11'
      alwaysOn: (appServiceSku != 'F1' && appServiceSku != 'D1')
      appSettings: [
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'CENTINELA_STORAGE_BACKEND'
          value: 'dual'
        }
        {
          name: 'CENTINELA_BLOB_ACCOUNT_URL'
          value: storageAccountBlobEndpoint
        }
        {
          name: 'CENTINELA_BLOB_CONTAINER_RAW_TRANSACTIONS'
          value: 'transacciones'
        }
        {
          name: 'CENTINELA_COSMOS_ACCOUNT_URL'
          value: cosmosAccountUrl
        }
        {
          name: 'CENTINELA_EVENT_PUBLISHER_BACKEND'
          value: 'eventgrid'
        }
        {
          name: 'CENTINELA_EVENT_GRID_TOPIC_ENDPOINT'
          value: eventGridTopicEndpoint
        }
        {
          // Limitación de tasa (sección 2.7) -- valores por defecto ya
          // cableados en app/core/config.py; se listan aquí explícitos
          // para que cambiarlos sea un cambio de App Setting, sin tocar
          // código (docs/limite-tasa-api.md).
          name: 'CENTINELA_RATE_LIMIT_WINDOW_SECONDS'
          value: '60'
        }
        {
          name: 'CENTINELA_RATE_LIMIT_MAX_REQUESTS'
          value: '60'
        }
      ]
    }
  }
}

output webAppId string = webApp.id
output webAppName string = webApp.name
output webAppPrincipalId string = webApp.identity.principalId
output webAppHostName string = webApp.properties.defaultHostName
