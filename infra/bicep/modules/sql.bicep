targetScope = 'resourceGroup'

// Almacén de casos relacional (Azure-Semana2.md, sección 2.2).
// Azure SQL Database, Serverless General Purpose con el Free Offer
// (useFreeLimit), AAD-only (sin usuario/contraseña SQL), aislado de
// internet mediante Service Endpoint restringido a snet-scoring (única
// subred que necesita tocar SQL en este diseño -- la API no accede
// directamente). Justificación completa y caveat de autenticación AAD vía
// pyodbc en docs/decisiones-arquitectura.md y docs/estrategia-respaldo-sql.md.
//
// NOTA: requiere un admin AAD en el momento de creación del servidor
// (`administrators`). Pasar el objectId/login de quien ejecuta el
// despliegue, obtenible con:
//   az ad signed-in-user show --query "{login:userPrincipalName, id:id}"

param prefix string
param env string
param instance string
param regionShort string
param location string = resourceGroup().location
param subnetScoringId string
param aadAdminLogin string
param aadAdminObjectId string

var serverName = toLower('sql-${prefix}-${env}-${regionShort}-${instance}')
var databaseName = 'centinela-casos'

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: serverName
  location: location
  properties: {
    administrators: {
      administratorType: 'ActiveDirectory'
      principalType: 'User'
      login: aadAdminLogin
      sid: aadAdminObjectId
      azureADOnlyAuthentication: true
    }
    publicNetworkAccess: 'Enabled'
    minimalTlsVersion: '1.2'
  }
}

resource sqlDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: databaseName
  location: location
  sku: {
    name: 'GP_S_Gen5'
    tier: 'GeneralPurpose'
    family: 'Gen5'
    capacity: 1
  }
  properties: {
    autoPauseDelay: 60
    minCapacity: json('0.5')
    // Free Offer de Azure SQL: hasta 100K vCore-seg/mes y 32GB gratis, uno
    // por suscripción -- riesgo de elegibilidad no verificable sin `az`
    // real (mismo tipo de riesgo que el Free Tier de Cosmos). Fallback si
    // no aplica: Basic (~$5/mes), sigue bajo el límite de $40 de la semana.
    useFreeLimit: true
    freeLimitExhaustionBehavior: 'AutoPause'
  }
}

resource vnetRule 'Microsoft.Sql/servers/virtualNetworkRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'allow-scoring-subnet'
  properties: {
    virtualNetworkSubnetId: subnetScoringId
    ignoreMissingVnetServiceEndpoint: false
  }
}

output serverName string = sqlServer.name
output serverFqdn string = sqlServer.properties.fullyQualifiedDomainName
output databaseName string = sqlDatabase.name