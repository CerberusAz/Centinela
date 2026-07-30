targetScope = 'resourceGroup'

// Almacén de transacciones NoSQL (Azure-Semana2.md, sección 2.1).
// Decisiones justificadas en docs/justificacion-particionamiento-cosmos.md
// y docs/decisiones-arquitectura.md (ADR de semana 2):
//   - Partición /account_id.
//   - Consistencia Session.
//   - TTL 30 días a nivel contenedor.
//   - Free Tier (1000 RU/s + 25GB) -- uno por suscripción, no verificable
//     sin `az` real; riesgo documentado.
//   - AAD-only (disableLocalAuth), sin claves.

param prefix string
param env string
param instance string
param regionShort string
param location string = resourceGroup().location
param subnetAppId string
param subnetScoringId string

var accountName = toLower(take('cosmos-${prefix}-${env}-${regionShort}-${instance}', 44))
var databaseName = 'centinela'
var containerName = 'transactions'
var ttlSeconds = 2592000 // 30 dias

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: accountName
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: true
    disableLocalAuth: true
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    // Mismo mecanismo gratuito que Storage (semana 1): Service Endpoint +
    // filtro de red, restringido a las subredes que realmente necesitan
    // acceso (snet-app escribe desde la API, snet-scoring lee/escribe
    // desde el motor de scoring). No Private Endpoint (~$7/mes) -- ver
    // docs/decisiones-arquitectura.md sobre la decisión de costo.
    publicNetworkAccess: 'Enabled'
    isVirtualNetworkFilterEnabled: true
    virtualNetworkRules: [
      {
        id: subnetAppId
        ignoreMissingVNetServiceEndpoint: false
      }
      {
        id: subnetScoringId
        ignoreMissingVNetServiceEndpoint: false
      }
    ]
    networkAclBypass: 'AzureServices'
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosAccount
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

resource container 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: containerName
  properties: {
    resource: {
      id: containerName
      partitionKey: {
        paths: [
          '/account_id'
        ]
        kind: 'Hash'
      }
      defaultTtl: ttlSeconds
    }
  }
}

output accountName string = cosmosAccount.name
output accountId string = cosmosAccount.id
output documentEndpoint string = cosmosAccount.properties.documentEndpoint