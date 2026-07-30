targetScope = 'resourceGroup'

// Semana 3: Registro de contenedores privado para las imágenes de la API,
// el motor de scoring y la Function de casos.
//
// SKU Basic: nivel gratuito de ACR que cubre el caso de uso de un proyecto
// de prueba (10 GB de almacenamiento, sin geo-replicación). Suficiente para
// imágenes Python con multi-stage build (~100-300 MB por imagen).
// Ver docs/reporte-imagenes.md para el análisis de tamaño de imágenes.
//
// adminUserEnabled: false — la autenticación al registry se realiza
// exclusivamente con la identidad gestionada de cada recurso que necesita
// hacer pull (Managed Identity + rol AcrPull), sin usuario/contraseña del
// registro. Consistente con el principio de cero credenciales del proyecto.

param prefix string
param env string
param instance string
param regionShort string
param location string = resourceGroup().location

// Los nombres de ACR solo admiten letras y números (sin guiones).
// Se elimina el prefijo 'cr' y se usa uniqueString para garantizar unicidad
// global (el nombre del ACR es un hostname DNS público).
var acrName = take('cr${prefix}${env}${regionShort}${instance}${uniqueString(resourceGroup().id)}', 50)

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
    zoneRedundancy: 'Disabled'
  }
}

output acrId string = containerRegistry.id
output acrName string = containerRegistry.name
output acrLoginServer string = containerRegistry.properties.loginServer
