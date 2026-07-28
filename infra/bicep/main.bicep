targetScope = 'subscription'

param prefix string = 'trial'
param env string = 'dev'
param instance string = '001'
param regionShort string = 'eus2'
param location string = 'eastus2'
param alertEmail string
@allowed([
  'F1'
  'B1'
])
param appServiceSku string = 'F1'

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

// 4. Cuenta de Almacenamiento
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

// 5. App Service (Web App y Plan)
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
  }
}

// 6. Asignaciones de Rol (RBAC)
module rbac 'modules/rbac.bicep' = {
  name: 'deploy-rbac'
  scope: rg
  params: {
    principalId: app.outputs.webAppPrincipalId
    storageAccountName: storage.outputs.storageAccountName
  }
}

output webAppName string = app.outputs.webAppName
output resourceGroupName string = rg.name
