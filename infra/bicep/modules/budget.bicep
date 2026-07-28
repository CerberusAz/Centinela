targetScope = 'subscription'

param prefix string
param env string
param instance string
param regionShort string
param amount int = 140
param contactEmails array

var budgetName = 'budget-${prefix}-${env}-${regionShort}-${instance}'

// Obtenemos el inicio del mes actual (utcNow solo es válido como valor por defecto de un parámetro en Bicep)
param startDate string = '${utcNow('yyyy-MM')}-01T00:00:00Z'
// Fin es un año después
var endDate = dateTimeAdd(startDate, 'P1Y')

resource budget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: budgetName
  properties: {
    category: 'Cost'
    amount: amount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: startDate
      endDate: endDate
    }
    notifications: {
      Alerta_50pct_Consumido: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 50
        contactEmails: contactEmails
        thresholdType: 'Actual'
      }
      Alerta_80pct_Consumido: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 80
        contactEmails: contactEmails
        thresholdType: 'Actual'
      }
      Alerta_100pct_Proyectado: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        contactEmails: contactEmails
        thresholdType: 'Forecasted'
      }
    }
  }
}
