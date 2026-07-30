targetScope = 'resourceGroup'

param prefix string
param env string
param instance string
param regionShort string
param location string = resourceGroup().location

var vnetName = 'vnet-${prefix}-${env}-${regionShort}-${instance}'
var vnetPrefix = '10.20.0.0/16'

var nsgAppName = 'nsg-${prefix}-${env}-${regionShort}-${instance}-app'
var nsgStorageName = 'nsg-${prefix}-${env}-${regionShort}-${instance}-st'
var nsgMgtName = 'nsg-${prefix}-${env}-${regionShort}-${instance}-mgt'
var nsgScoringName = 'nsg-${prefix}-${env}-${regionShort}-${instance}-scoring'

resource nsgApp 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: nsgAppName
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowManagementToAppService'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.20.5.0/24'
          sourcePortRange: '*'
          destinationAddressPrefix: '10.20.1.0/24'
          destinationPortRange: '443'
          description: 'Administracion'
        }
      }
      {
        name: 'AllowAppServiceToStorageOutbound'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.20.1.0/24'
          sourcePortRange: '*'
          destinationAddressPrefix: '10.20.2.0/24'
          destinationPortRange: '443'
          description: 'Permitir trafico de salida hacia Storage y Queue'
        }
      }
      {
        name: 'AllowAppServiceToCosmosDbOutbound'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.20.1.0/24'
          sourcePortRange: '*'
          destinationAddressPrefix: 'AzureCosmosDB'
          destinationPortRange: '443'
          description: 'Semana 2: escritura dual de la transaccion en Cosmos DB (DualTransactionStorage)'
        }
      }
      {
        name: 'AllowAppServiceToEventGridOutbound'
        properties: {
          priority: 120
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.20.1.0/24'
          sourcePortRange: '*'
          destinationAddressPrefix: 'AzureEventGrid'
          destinationPortRange: '443'
          description: 'Semana 2: publicar el evento transaction.received (EventGridEventPublisher)'
        }
      }
      {
        name: 'DenyAllVnetInbound'
        properties: {
          priority: 4095
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
          description: 'Principio Menor Acceso'
        }
      }
    ]
  }
}

resource nsgScoring 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: nsgScoringName
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowScoringToCosmosDbOutbound'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.20.4.0/24'
          sourcePortRange: '*'
          destinationAddressPrefix: 'AzureCosmosDB'
          destinationPortRange: '443'
          description: 'Motor de scoring: leer historial y persistir score en Cosmos DB'
        }
      }
      {
        name: 'AllowScoringToSqlOutbound'
        properties: {
          priority: 110
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.20.4.0/24'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Sql'
          destinationPortRange: '1433'
          description: 'Function de casos: insertar en el almacen de casos (Azure SQL)'
        }
      }
      {
        name: 'AllowScoringToServiceBusOutbound'
        properties: {
          priority: 120
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.20.4.0/24'
          sourcePortRange: '*'
          destinationAddressPrefix: 'ServiceBus'
          destinationPortRange: '443'
          description: 'Motor de scoring: publicar en la cola casos-marcados; Function de casos: consumirla'
        }
      }
      {
        name: 'DenyAllVnetInbound'
        properties: {
          priority: 4095
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
          description: 'Principio Menor Acceso'
        }
      }
    ]
  }
}

resource nsgStorage 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: nsgStorageName
  location: location
  properties: {
    securityRules: [
      {
        name: 'AllowAppServiceToBlob'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.20.1.0/24'
          sourcePortRange: '*'
          destinationAddressPrefix: '10.20.2.0/24'
          destinationPortRange: '443'
          description: 'Guardar transacciones'
        }
      }
      {
        name: 'AllowAppServiceToQueue'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: '10.20.1.0/24'
          sourcePortRange: '*'
          destinationAddressPrefix: '10.20.2.0/24'
          destinationPortRange: '443'
          description: 'Enviar mensajes'
        }
      }
      {
        name: 'DenyInternetToStorage'
        properties: {
          priority: 4000
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '10.20.2.0/24'
          destinationPortRange: '*'
          description: 'Bloqueado por seguridad'
        }
      }
      {
        name: 'DenyStorageToInternet'
        properties: {
          priority: 4000
          direction: 'Outbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '10.20.2.0/24'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Internet'
          destinationPortRange: '*'
          description: 'Bloqueado por seguridad'
        }
      }
      {
        name: 'DenyAllVnetInbound'
        properties: {
          priority: 4095
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
          description: 'Principio Menor Acceso'
        }
      }
    ]
  }
}

resource nsgMgt 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: nsgMgtName
  location: location
  properties: {
    securityRules: []
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetPrefix
      ]
    }
    subnets: [
      {
        name: 'snet-${prefix}-${env}-${regionShort}-${instance}-app'
        properties: {
          addressPrefix: '10.20.1.0/24'
          networkSecurityGroup: {
            id: nsgApp.id
          }
          delegations: [
            {
              name: 'Microsoft.Web.serverFarms'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
          serviceEndpoints: [
            {
              service: 'Microsoft.Storage'
            }
            {
              service: 'Microsoft.AzureCosmosDB'
            }
          ]
        }
      }
      {
        name: 'snet-${prefix}-${env}-${regionShort}-${instance}-st'
        properties: {
          addressPrefix: '10.20.2.0/24'
          networkSecurityGroup: {
            id: nsgStorage.id
          }
        }
      }
      {
        name: 'snet-${prefix}-${env}-${regionShort}-${instance}-db'
        properties: {
          addressPrefix: '10.20.3.0/24'
        }
      }
      {
        name: 'snet-${prefix}-${env}-${regionShort}-${instance}-scoring'
        properties: {
          addressPrefix: '10.20.4.0/24'
          networkSecurityGroup: {
            id: nsgScoring.id
          }
          delegations: [
            {
              name: 'Microsoft.Web.serverFarms'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
          serviceEndpoints: [
            {
              service: 'Microsoft.AzureCosmosDB'
            }
            {
              service: 'Microsoft.Sql'
            }
            {
              service: 'Microsoft.ServiceBus'
            }
          ]
        }
      }
      {
        name: 'snet-${prefix}-${env}-${regionShort}-${instance}-mgt'
        properties: {
          addressPrefix: '10.20.5.0/24'
          networkSecurityGroup: {
            id: nsgMgt.id
          }
        }
      }
    ]
  }
}

output vnetId string = vnet.id
output vnetName string = vnet.name
output subnetAppId string = vnet.properties.subnets[0].id
output subnetStorageId string = vnet.properties.subnets[1].id
output subnetScoringId string = vnet.properties.subnets[3].id
