targetScope = 'subscription'

param prefix string = 'trial'
param env string = 'dev'
param instance string = '001'
param regionShort string = 'weu'
param location string = 'westeurope'
param alertEmail string
@allowed([
  'F1'
  'B1'
])
param appServiceSku string = 'F1'

// Semana 2 -- admin AAD requerido por Azure SQL (azureADOnlyAuthentication).
// Obtenido con: az ad signed-in-user show --query "{login:userPrincipalName, id:id}"
param sqlAadAdminLogin string
param sqlAadAdminObjectId string

var rgName = 'rg-${prefix}-${env}-${regionShort}-${instance}'

// 1. Grupo de Recursos
resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: rgName
  location: location
}

// 2. Presupuesto (Scope: Suscripción)
module budget 'modules/budget.bicep' = {
  name: 'deploy-budget-${regionShort}'
  params: {
    prefix: prefix
    env: env
    instance: instance
    regionShort: regionShort
    contactEmails: [
      alertEmail
    ]
  }
}

// 3. Red Virtual y Subredes
module network 'modules/network.bicep' = {
  name: 'deploy-network'
  scope: rg
  params: {
    prefix: prefix
    env: env
    instance: instance
    regionShort: regionShort
    location: location
  }
}

// 4. Cuenta de Almacenamiento (semana 1: transacciones crudas, documentos, colas)
module storage 'modules/storage.bicep' = {
  name: 'deploy-storage'
  scope: rg
  params: {
    prefix: prefix
    env: env
    instance: instance
    regionShort: regionShort
    location: location
    subnetAppId: network.outputs.subnetAppId
  }
}

// 5. Cosmos DB (semana 2: store operativo de transacciones/scores)
module cosmos 'modules/cosmos.bicep' = {
  name: 'deploy-cosmos'
  scope: rg
  params: {
    prefix: prefix
    env: env
    instance: instance
    regionShort: regionShort
    location: location
    subnetAppId: network.outputs.subnetAppId
    subnetScoringId: network.outputs.subnetScoringId
  }
}

// 6. Azure SQL (semana 2: almacén de casos)
module sql 'modules/sql.bicep' = {
  name: 'deploy-sql'
  scope: rg
  params: {
    prefix: prefix
    env: env
    instance: instance
    regionShort: regionShort
    location: location
    subnetScoringId: network.outputs.subnetScoringId
    aadAdminLogin: sqlAadAdminLogin
    aadAdminObjectId: sqlAadAdminObjectId
  }
}

// 7. Event Grid + Service Bus (semana 2: mensajería)
module eventing 'modules/eventing.bicep' = {
  name: 'deploy-eventing'
  scope: rg
  params: {
    prefix: prefix
    env: env
    instance: instance
    regionShort: regionShort
    location: location
  }
}

// 8. App Service (Web App y Plan) -- API de ingesta
module app 'modules/app.bicep' = {
  name: 'deploy-app'
  scope: rg
  params: {
    prefix: prefix
    env: env
    instance: instance
    regionShort: regionShort
    location: location
    subnetAppId: network.outputs.subnetAppId
    storageAccountBlobEndpoint: storage.outputs.storageAccountBlobEndpoint
    appServiceSku: appServiceSku
    cosmosAccountUrl: cosmos.outputs.documentEndpoint
    eventGridTopicEndpoint: eventing.outputs.eventGridTopicEndpoint
  }
}

// 9. Functions (semana 2: motor de scoring + creación de casos)
module functions 'modules/functions.bicep' = {
  name: 'deploy-functions'
  scope: rg
  params: {
    prefix: prefix
    env: env
    instance: instance
    regionShort: regionShort
    location: location
    subnetScoringId: network.outputs.subnetScoringId
    eventGridTopicName: eventing.outputs.eventGridTopicName
    cosmosAccountUrl: cosmos.outputs.documentEndpoint
    cosmosDatabaseName: 'centinela'
    cosmosContainerTransactions: 'transactions'
    serviceBusNamespaceFqdn: eventing.outputs.serviceBusNamespaceFqdn
    casosQueueName: eventing.outputs.casosQueueName
    sqlServerFqdn: sql.outputs.serverFqdn
    sqlDatabaseName: sql.outputs.databaseName
  }
}

// 10. Asignaciones de Rol (RBAC) -- Web App + ambas Functions
module rbac 'modules/rbac.bicep' = {
  name: 'deploy-rbac'
  scope: rg
  params: {
    principalId: app.outputs.webAppPrincipalId
    storageAccountName: storage.outputs.storageAccountName
    cosmosAccountName: cosmos.outputs.accountName
    eventGridTopicName: eventing.outputs.eventGridTopicName
    serviceBusNamespaceName: eventing.outputs.serviceBusNamespaceName
    scoringFunctionPrincipalId: functions.outputs.scoringFunctionPrincipalId
    casesFunctionPrincipalId: functions.outputs.casesFunctionPrincipalId
    functionsStorageAccountName: functions.outputs.functionsStorageAccountName
  }
}

output webAppName string = app.outputs.webAppName
output resourceGroupName string = rg.name
output scoringFunctionAppName string = functions.outputs.scoringFunctionAppName
output casesFunctionAppName string = functions.outputs.casesFunctionAppName
output cosmosAccountName string = cosmos.outputs.accountName
output sqlServerFqdn string = sql.outputs.serverFqdn