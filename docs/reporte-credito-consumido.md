# Reporte de crédito consumido

Entregable 24. Persona 1.

## 1. Estado de este reporte

Este documento define la metodología y consigna los datos disponibles en
el repositorio. **El monto real consumido no está verificado**: requiere
una consulta en vivo contra la suscripción de Azure, que no se ejecutó al
redactar este documento. Se deja el comando exacto a correr y dónde volcar
el resultado, siguiendo el mismo criterio de `[VERIFICAR]` ya usado en
`docs/nivel-servicio-costo.md` §2 para no reportar una cifra no
verificada como si fuera real.

**Comando a ejecutar para completar la sección 2:**

```bash
az consumption usage list \
  --start-date <YYYY-MM-DD> \
  --end-date <YYYY-MM-DD> \
  --query "[].{recurso:instanceName, costo:pretaxCost, moneda:currency}" \
  -o table
```

o, si el proveedor `Microsoft.CostManagement` está disponible en la
suscripción de prueba:

```bash
az costmanagement query \
  --type ActualCost \
  --timeframe MonthToDate \
  --scope "/subscriptions/<sub-id>" \
  --dataset-aggregation '{"totalCost":{"name":"PreTaxCost","function":"Sum"}}'
```

## 2. Consumo real — `[VERIFICAR]`

| Concepto | Valor |
|---|---|
| Crédito consumido a la fecha | `[VERIFICAR — ejecutar comando de §1]` |
| % del presupuesto mensual ($140, `budget.bicep:7`) | `[VERIFICAR]` |
| ¿Bajo el límite de $20 USD para semana 1 (criterio de aceptación)? | `[VERIFICAR]` |

## 3. Estimado de referencia (no es consumo real)

`README.md` y `docs/nivel-servicio-costo.md` documentan un **estimado**
para el patrón de infraestructura de la semana 1 en un despliegue limpio
de 21 días:

| Componente | Estimado (21 días) |
|---|---|
| App Service Plan B1 Linux | ~$9.50 – $13.50 USD |
| Storage Account (Standard_LRS) | ~$0.10 – $0.50 USD |
| VNet / Subredes / NSGs / Service Endpoints | $0.00 USD |
| **Total estimado (camino feliz, un solo despliegue)** | **~$10.00 – $14.00 USD** |

La tarifa horaria exacta de B1 en `westeurope` sigue marcada
`[VERIFICAR]` en `docs/nivel-servicio-costo.md:59` — este estimado hereda
esa misma incertidumbre y debe tratarse como orden de magnitud, no como
cifra final.

## 4. Por qué el consumo real probablemente sea mayor al estimado de §3

El estimado de §3 asume un único despliegue limpio. El historial real de
la sesión de depuración (`Fixing Bicep Budget Deployment Errors.md`)
muestra que el aprovisionamiento no fue de un solo intento:

- Al menos 3 ciclos completos de `deploy-all.sh` sobre resource groups
  distintos (`rg-trial-dev-weu-001`, `-002`, `-003`), cada uno
  provisionando App Service Plan + Storage Account + VNet completos antes
  de ser reemplazado (líneas 201, 245, 267 del chat).
- Múltiples resource groups de prueba de cuota, creados y eliminados
  durante el diagnóstico de la región (`rg-test-quota`, `rg-test-quota-eus`,
  `rg-test-quota-scus`, `rg-quota-westus2`, `rg-quota-westeurope`,
  `rg-quota-northeurope`, `rg-quota-centralus`, `rg-quota-canadacentral`,
  `rg-quota-brazilsouth`, `rg-quota-uksouth`), cada uno con al menos un
  App Service Plan de prueba (líneas 107-157).

Estos recursos de prueba se eliminaron con `--no-wait` poco después de
crearse, por lo que su contribución al costo es previsiblemente pequeña
(minutos u horas de existencia, no días) — pero no es cero, y no está
incluida en el estimado de §3. **Esta es la razón concreta por la que la
cifra de §2 debe verificarse contra la facturación real y no asumirse
igual al estimado de §3.**

## 5. Proyección a 3 semanas

La proyección completa depende de decisiones de arquitectura que
`docs/informe-cuotas.md` §5 deja explícitamente pendientes para semana 2
(selección de Cosmos DB vs. SQL — cuota no evaluada todavía). Por eso la
proyección se dan en dos partes:

| Semana | Componentes con costo conocido | Estimado |
|---|---|---|
| 1 (actual) | App Service B1 + Storage LRS + red | Ver §3: ~$10–$14 (estimado, no verificado) |
| 2 | + almacén relacional/documental (Cosmos DB o SQL, sin seleccionar) + Document Intelligence F0 (gratuito hasta 500 páginas/mes, `docs/informe-cuotas.md` §2) | **No proyectable todavía** — depende de la selección de almacén, pendiente |
| 3 | + escalado (posible upgrade de SKU si el informe de cuotas o la carga lo justifican) | **No proyectable todavía** — depende del resultado de semana 2 |

**Control aplicable a las 3 semanas, ya configurado:** el presupuesto de
`$140` mensual con alertas al 50% ($70), 80% ($112) y 100% proyectado
(`budget.bicep:28-49`, `docs/informe-cuotas.md` §4) actúa como techo común
para las tres semanas, independientemente de que la proyección detallada
de semanas 2 y 3 todavía no se pueda completar.

## 6. Acción pendiente para cerrar este entregable

1. Ejecutar el comando de §1 contra la suscripción activa y completar §2.
2. Repetir la consulta al cierre de cada semana para no perder la
   comparación con el estimado de §3.
3. Una vez seleccionado el almacén de datos de semana 2 (bloqueado en
   `docs/informe-cuotas.md` §5), volver a esta sección y completar la
   proyección de §5.
