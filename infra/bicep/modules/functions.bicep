targetScope = 'resourceGroup'

// Componentes serverless de semana 2 (Azure-Semana2.md, sección 2.3):
// motor de scoring (scoring/) y creación de casos (cases/), cada uno un
// Function App independiente -- el diagrama de dependencias de
// semana2.txt los trata como componentes de despliegue distintos, no como
// parte de la Web App de la API.
//
// Ambos: Consumption (Y1, serverless -- coherente con "Componente
// serverless" de la sección 2.3), Linux, Python 3.11, Managed Identity
// SystemAssigned, integrados a snet-scoring (reservada exactamente para
// esto en semana 1).

param prefix string
param env string
param instance string
param regionShort string
param location string = resourceGroup().location
param subnetScoringId string
param eventGridTopicName string
param cosmosAccountUrl string
param cosmosDatabaseName string
param cosmosContainerTransactions string
param serviceBusNamespaceFqdn string
param casosQueueName string
param sqlServerFqdn string
param sqlDatabaseName string

var functionsStorageAccountName = take(
  'stfn${prefix}${env}${regionShort}${instance}${uniqueString(resourceGroup().id)}', 24
)
var scoringPlanName = 'plan-scoring-${prefix}-${env}-${regionShort}-${instance}'
var scoringFunctionAppName = 'func-scoring-${prefix}-${env}-${regionShort}-${instance}'
var casesPlanName = 'plan-cases-${prefix}-${env}-${regionShort}-${instance}'
var casesFunctionAppName = 'func-cases-${prefix}-${env}-${regionShort}-${instance}'

// Storage propia para el runtime de las Functions (AzureWebJobsStorage) --
// separada de la cuenta de storage.bicep para no mezclar el ciclo de vida
// operativo de las Functions con el de los datos de negocio (blobs de
// transacciones/documentos, colas de semana 1).
resource functionsStorage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: functionsStorageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
  }
}

resource scoringPlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: scoringPlanName
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  properties: {
    reserved: true
  }
  kind: 'functionapp,linux'
}

resource scoringFunctionApp 'Microsoft.Web/sites@2022-09-01' = {
  name: scoringFunctionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: scoringPlan.id
    virtualNetworkSubnetId: subnetScoringId
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appSettings: [
        // AzureWebJobsStorage por identidad gestionada, sin clave de
        // cuenta -- requiere los roles de datos asignados en rbac.bicep.
        { name: 'AzureWebJobsStorage__accountName', value: functionsStorage.name }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'CENTINELA_SCORING_COSMOS_ACCOUNT_URL', value: cosmosAccountUrl }
        { name: 'CENTINELA_SCORING_COSMOS_DATABASE_NAME', value: cosmosDatabaseName }
        { name: 'CENTINELA_SCORING_COSMOS_CONTAINER_TRANSACTIONS', value: cosmosContainerTransactions }
        { name: 'CENTINELA_SCORING_SERVICEBUS_NAMESPACE_FQDN', value: serviceBusNamespaceFqdn }
        { name: 'CENTINELA_SCORING_SERVICEBUS_QUEUE_CASOS', value: casosQueueName }
      ]
    }
  }
}

resource casesPlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: casesPlanName
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  properties: {
    reserved: true
  }
  kind: 'functionapp,linux'
}

resource casesFunctionApp 'Microsoft.Web/sites@2022-09-01' = {
  name: casesFunctionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: casesPlan.id
    virtualNetworkSubnetId: subnetScoringId
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appSettings: [
        { name: 'AzureWebJobsStorage__accountName', value: functionsStorage.name }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        // Binding del trigger de Service Bus por identidad gestionada
        // (convención Azure Functions: <NombreConexion>__fullyQualifiedNamespace).
        { name: 'ServiceBusConnection__fullyQualifiedNamespace', value: serviceBusNamespaceFqdn }
        { name: 'CENTINELA_CASES_SQL_SERVER', value: sqlServerFqdn }
        { name: 'CENTINELA_CASES_SQL_DATABASE', value: sqlDatabaseName }
      ]
    }
  }
}



output scoringFunctionAppName string = scoringFunctionApp.name
output scoringFunctionPrincipalId string = scoringFunctionApp.identity.principalId
output casesFunctionAppName string = casesFunctionApp.name
output casesFunctionPrincipalId string = casesFunctionApp.identity.principalId
output functionsStorageAccountName string = functionsStorage.name
