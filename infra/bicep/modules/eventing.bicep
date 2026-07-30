targetScope = 'resourceGroup'

// Capa de mensajería de semana 2 (Azure-Semana2.md, sección 2.4) -- DOS
// mecanismos con propósito distinto, comparados en
// docs/mensajeria-semana2.md:
//   - Event Grid (topic personalizado): distribución del evento de
//     transacción. Notifica, no garantiza indefinidamente.
//   - Service Bus (tier Basic): cola de casos marcados. Garantiza entrega
//     at-least-once con dead-lettering nativo (maxDeliveryCount).
//
// Ambos con disableLocalAuth donde aplica -- sin claves compartidas, solo
// AAD (roles asignados en modules/rbac.bicep).

param prefix string
param env string
param instance string
param regionShort string
param location string = resourceGroup().location
param subnetScoringId string

var eventGridTopicName = 'evt-${prefix}-${env}-${regionShort}-${instance}'
var serviceBusNamespaceName = 'sb-${prefix}-${env}-${regionShort}-${instance}'
var casosQueueName = 'casos-marcados'

resource eventGridTopic 'Microsoft.EventGrid/topics@2023-12-15-preview' = {
  name: eventGridTopicName
  location: location
  properties: {
    inputSchema: 'EventGridSchema'
    // Event Grid no admite restricción por Service Endpoint de VNet como
    // Storage/Cosmos/SQL; el productor (Web App) se autentica por AAD
    // (rol "EventGrid Data Sender"), no por origen de red.
    publicNetworkAccess: 'Enabled'
  }
}

resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: serviceBusNamespaceName
  location: location
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
  properties: {
    // disableLocalAuth (forzar AAD, sin claves SAS) es una propiedad de
    // seguridad a nivel de namespace, no una función premium -- debería
    // aplicar también en Basic. No verificado contra Azure real en este
    // entorno; si el despliegue lo rechaza, es el primer valor a revisar.
    disableLocalAuth: true
  }
}

// Defensa en profundidad, mismo patrón que Storage/Cosmos/SQL: aunque
// disableLocalAuth ya exige AAD, se restringe además el origen de red a
// la subred que realmente necesita tocar Service Bus (snet-scoring).
resource serviceBusNetworkRules 'Microsoft.ServiceBus/namespaces/networkRuleSets@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'default'
  properties: {
    defaultAction: 'Deny'
    virtualNetworkRules: [
      {
        subnet: {
          id: subnetScoringId
        }
        ignoreMissingVnetServiceEndpoint: false
      }
    ]
  }
}

resource casosQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: casosQueueName
  properties: {
    // Dead-lettering NATIVO tras 5 intentos fallidos -- a diferencia de la
    // política manual sobre Storage Queue de semana 1
    // (docs/garantias-entrega-cola.md), Service Bus lo resuelve la
    // plataforma, no el consumidor. Mismo umbral de 5 por continuidad de
    // criterio con esa decisión de semana 1.
    maxDeliveryCount: 5
    lockDuration: 'PT1M'
    defaultMessageTimeToLive: 'P14D'
    deadLetteringOnMessageExpiration: true
  }
}

output eventGridTopicName string = eventGridTopic.name
output eventGridTopicEndpoint string = eventGridTopic.properties.endpoint
output serviceBusNamespaceName string = serviceBusNamespace.name
output serviceBusNamespaceFqdn string = '${serviceBusNamespace.name}.servicebus.windows.net'
output casosQueueName string = casosQueue.name