targetScope = 'resourceGroup'

// Semana 1: Managed Identity de la Web App sobre la Storage Account.
param storageAccountName string
param principalId string

// Semana 2: identidades adicionales y recursos nuevos. Todos los GUID de
// rol nuevos aquí abajo (Cosmos, Event Grid, Service Bus, Storage Table)
// se copiaron de la documentación pública de Azure y NO se verificaron
// contra `az role definition list` en este entorno (sin `az` disponible) --
// mismo tipo de riesgo que ya se materializó una vez en este proyecto
// (ver "Fixing Bicep Budget Deployment Errors.md", GUID corrupto de
// Storage Queue Data Contributor). Verificar antes del primer despliegue
// real con:
//   az role definition list --name "<nombre del rol>" --query "[0].name" -o tsv
param cosmosAccountName string
param eventGridTopicName string
param serviceBusNamespaceName string
param scoringFunctionPrincipalId string
param casesFunctionPrincipalId string
param explainerFunctionPrincipalId string  // Semana 3
param functionsStorageAccountName string
param acrName string   // Semana 3: registro privado de imágenes

// --- Roles de semana 1 (verificados en su momento) -------------------------
// Storage Blob Data Contributor
var blobContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
// Storage Queue Data Contributor
var queueContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'

// --- Roles de semana 2 (sin verificar, ver nota arriba) --------------------
// Cosmos DB Built-in Data Contributor -- rol de datos SQL API de Cosmos,
// identificador fijo bien conocido (distinto al resto: no es un
// Microsoft.Authorization/roleDefinitions de suscripción, es un
// sqlRoleDefinition dentro de la propia cuenta de Cosmos).
var cosmosDataContributorRoleId = '00000000-0000-0000-0000-000000000002'
// EventGrid Data Sender
var eventGridDataSenderRoleId = 'd5a91429-5739-47e2-a06b-3470a27159e7'
// Azure Service Bus Data Sender
var serviceBusDataSenderRoleId = '69a216fc-b8fb-44d8-bc22-1f3c2cd27a39'
// Azure Service Bus Data Receiver
var serviceBusDataReceiverRoleId = '4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0'
// Storage Blob Data Owner (AzureWebJobsStorage por identidad requiere Owner, no solo Contributor)
var blobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
// Storage Table Data Contributor (AzureWebJobsStorage usa Tables para checkpoints/locks)
var tableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
// AcrPull — permite hacer docker pull desde Azure Container Registry
// sin usuario/contraseña, usando la Managed Identity del recurso.
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageAccountName
}

resource functionsStorageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: functionsStorageAccountName
}

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: cosmosAccountName
}

resource eventGridTopic 'Microsoft.EventGrid/topics@2023-12-15-preview' existing = {
  name: eventGridTopicName
}

resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' existing = {
  name: serviceBusNamespaceName
}

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

// --- Web App (rol Servicio, semana 1) --------------------------------------

resource roleAssignmentBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, principalId, blobContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobContributorRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource roleAssignmentQueue 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, principalId, queueContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', queueContributorRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Web App (semana 2: escritura dual en Cosmos + publicar evento) --------

resource roleAssignmentWebAppCosmos 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  name: guid(cosmosAccount.id, principalId, cosmosDataContributorRoleId)
  parent: cosmosAccount
  properties: {
    roleDefinitionId: resourceId(
      'Microsoft.DocumentDB/databaseAccounts/sqlRoleDefinitions', cosmosAccount.name, cosmosDataContributorRoleId
    )
    principalId: principalId
    scope: cosmosAccount.id
  }
}

resource roleAssignmentWebAppEventGrid 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(eventGridTopic.id, principalId, eventGridDataSenderRoleId)
  scope: eventGridTopic
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', eventGridDataSenderRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Motor de scoring (Function) --------------------------------------------

resource roleAssignmentScoringCosmos 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  name: guid(cosmosAccount.id, scoringFunctionPrincipalId, cosmosDataContributorRoleId)
  parent: cosmosAccount
  properties: {
    roleDefinitionId: resourceId(
      'Microsoft.DocumentDB/databaseAccounts/sqlRoleDefinitions', cosmosAccount.name, cosmosDataContributorRoleId
    )
    principalId: scoringFunctionPrincipalId
    scope: cosmosAccount.id
  }
}

resource roleAssignmentScoringServiceBusSend 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(serviceBusNamespace.id, scoringFunctionPrincipalId, serviceBusDataSenderRoleId)
  scope: serviceBusNamespace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', serviceBusDataSenderRoleId)
    principalId: scoringFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource roleAssignmentScoringBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionsStorageAccount.id, scoringFunctionPrincipalId, blobDataOwnerRoleId)
  scope: functionsStorageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataOwnerRoleId)
    principalId: scoringFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource roleAssignmentScoringQueue 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionsStorageAccount.id, scoringFunctionPrincipalId, queueContributorRoleId)
  scope: functionsStorageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', queueContributorRoleId)
    principalId: scoringFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource roleAssignmentScoringTable 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionsStorageAccount.id, scoringFunctionPrincipalId, tableDataContributorRoleId)
  scope: functionsStorageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', tableDataContributorRoleId)
    principalId: scoringFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// --- Function de creación de casos ------------------------------------------

resource roleAssignmentCasesServiceBusReceive 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(serviceBusNamespace.id, casesFunctionPrincipalId, serviceBusDataReceiverRoleId)
  scope: serviceBusNamespace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', serviceBusDataReceiverRoleId)
    principalId: casesFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource roleAssignmentCasesBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionsStorageAccount.id, casesFunctionPrincipalId, blobDataOwnerRoleId)
  scope: functionsStorageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataOwnerRoleId)
    principalId: casesFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource roleAssignmentCasesQueue 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionsStorageAccount.id, casesFunctionPrincipalId, queueContributorRoleId)
  scope: functionsStorageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', queueContributorRoleId)
    principalId: casesFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource roleAssignmentCasesTable 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionsStorageAccount.id, casesFunctionPrincipalId, tableDataContributorRoleId)
  scope: functionsStorageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', tableDataContributorRoleId)
    principalId: casesFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// NOTA -- paso manual pendiente, no expresable en Bicep (ver
// docs/decisiones-arquitectura.md): además de este RBAC de Azure, la
// Function de casos necesita un usuario de base de datos dentro de Azure
// SQL creado con:
//   CREATE USER [<nombre-managed-identity-cases-function>] FROM EXTERNAL PROVIDER;
//   ALTER ROLE db_datareader ADD MEMBER [<nombre-managed-identity-cases-function>];
//   ALTER ROLE db_datawriter ADD MEMBER [<nombre-managed-identity-cases-function>];
// Ejecutado una sola vez contra la base real, con una identidad que ya sea
// administradora AAD del servidor (ver modules/sql.bicep).

// --- ACR Pull (semana 3) — los 3 recursos hacen docker pull desde el ACR ---

resource roleAssignmentApiAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, principalId, acrPullRoleId)
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource roleAssignmentScoringAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, scoringFunctionPrincipalId, acrPullRoleId)
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: scoringFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource roleAssignmentCasesAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, casesFunctionPrincipalId, acrPullRoleId)
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: casesFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource roleAssignmentExplainerAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerRegistry.id, explainerFunctionPrincipalId, acrPullRoleId)
  scope: containerRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: explainerFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// --- Roles de Storage para el runtime de las Functions ---

resource roleAssignmentExplainerBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionsStorageAccount.id, explainerFunctionPrincipalId, blobDataOwnerRoleId)
  scope: functionsStorageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataOwnerRoleId)
    principalId: explainerFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource roleAssignmentExplainerQueue 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionsStorageAccount.id, explainerFunctionPrincipalId, queueContributorRoleId)
  scope: functionsStorageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', queueContributorRoleId)
    principalId: explainerFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource roleAssignmentExplainerTable 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(functionsStorageAccount.id, explainerFunctionPrincipalId, tableDataContributorRoleId)
  scope: functionsStorageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', tableDataContributorRoleId)
    principalId: explainerFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// --- Roles de Service Bus para el explicador ---

resource roleAssignmentExplainerServiceBus 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(serviceBusNamespace.id, explainerFunctionPrincipalId, serviceBusDataReceiverRoleId)
  scope: serviceBusNamespace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', serviceBusDataReceiverRoleId)
    principalId: explainerFunctionPrincipalId
    principalType: 'ServicePrincipal'
  }
}