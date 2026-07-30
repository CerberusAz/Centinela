# Reporte de crédito consumido — Semana 2

Entregable 13 de semana 2 ("Reporte de crédito consumido. Acumulado y
proyección al cierre del proyecto"). Complementa, no reemplaza,
`docs/reporte-credito-consumido.md` (semana 1) — ese documento ya dejó la
metodología y el comando exacto de consulta; este añade los componentes
nuevos y la proyección al cierre del proyecto (fin de semana 3).

## 1. Estado de este reporte

Igual que en semana 1: **el monto real consumido no está verificado**.
Requiere una consulta en vivo contra la suscripción de Azure, no
ejecutable desde este entorno de desarrollo (sin `az login`). Mismo
comando de referencia que semana 1:

```bash
az consumption usage list \
  --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> \
  --query "[].{recurso:instanceName, costo:pretaxCost, moneda:currency}" \
  -o table
```

## 2. Consumo acumulado (semana 1 + semana 2) — `[VERIFICAR]`

| Concepto | Valor |
|---|---|
| Crédito consumido semana 1 | `[VERIFICAR]` — ver `docs/reporte-credito-consumido.md` §2 |
| Crédito consumido semana 2 | `[VERIFICAR]` |
| Crédito acumulado total | `[VERIFICAR]` |
| % del presupuesto mensual ($140) | `[VERIFICAR]` |
| ¿Bajo el límite de $40 USD acumulado a semana 2? | `[VERIFICAR]` |

## 3. Estimado de referencia de los componentes nuevos (no es consumo real)

Este estimado refleja los componentes **efectivamente desplegados** en el
despliegue real de semana 2 (grupo `rg-trial-dev-cus-003`, región `centralus`).
En varios casos el estimado inicial cambió por las decisiones documentadas
en ADR-022 (`docs/decisiones-arquitectura.md`):

| Componente | Estimado | Nota |
|---|---|---|
| Cosmos DB (sin Free Tier) | ~$1.00/día | Free Tier no aplicable (ADR-022a). Depende del consumo de RU y almacenamiento real |
| Azure SQL (Basic, ~5 DTU) | ~$5/mes | Serverless Free Offer no disponible; desplegado en tier Basic, el más económico disponible |
| Event Grid | Centavos | Pay-per-operation, volumen de prueba |
| Service Bus (Basic) | Centavos | Pay-per-operation, sin costo base |
| 3 App Service Plans B1 (API + Scoring + Casos) | ~$0.018/h cada uno | Functions migradas a B1 por VNet Integration (ADR-022b). 3 planes × ~$0.018 USD/h = ~$0.054 USD/h |
| Storage Account de runtime (Functions) | ~$0.10 | LRS, mínimo tráfico |
| **Total estimado, componentes nuevos** | **~$1.50-$2.50 USD/día** | Dominado por Cosmos DB (~$1/día) y los 3 planes B1 (~$1.30/día a 24h). Apagar el grupo de recursos por las noches reduce el impacto de los B1 |

Sumado al estimado de semana 1 (~$10-$14 acumulado), el estimado actualizado
cumple el límite de $40 USD si el grupo de recursos se destruye al terminar
la semana 2 (21 días máximos de operación, con apagado nocturno activo).

## 4. Por qué el consumo real de semana 2 probablemente sea mayor al estimado

Mismo patrón que semana 1 (`docs/reporte-credito-consumido.md` §4): el
estimado de §3 asume un despliegue limpio de un solo intento. La
infraestructura de semana 2 (`cosmos.bicep`, `sql.bicep`,
`eventing.bicep`, `functions.bicep`, más los cambios en `network.bicep`/
`rbac.bicep`/`app.bicep`) nunca se desplegó contra Azure real desde este
entorno — no hay todavía un historial de iteraciones de depuración como
el de semana 1 (`Fixing Bicep Budget Deployment Errors.md`) que
cuantificar, pero es razonable esperar que el primer despliegue real
tenga al menos una ronda de ajustes (los GUID de rol nuevos en
`rbac.bicep` están explícitamente marcados como no verificados contra
`az role definition list` — un error ahí sería el candidato más probable
al primer fallo de despliegue, igual que ocurrió con el GUID de Storage
Queue Data Contributor en semana 1).

## 5. Proyección al cierre del proyecto (fin de semana 3)

| Semana | Componentes con costo conocido | Estimado |
|---|---|---|
| 1 | App Service B1 + Storage LRS + red | ~$10-$14 (no verificado) |
| 2 | + Cosmos DB (Free Tier) + Azure SQL (Free Offer) + Event Grid + Service Bus (Basic) + 2 Functions (Consumption) + Storage runtime | Unos pocos USD adicionales (no verificado) |
| 3 | Fuera de alcance de este documento — depende de las decisiones de escalado de semana 3 (`Azure-Semana3.md`, no leído en esta sesión) | **No proyectable todavía** |

**Control aplicable a las 3 semanas, ya configurado desde semana 1:** el
presupuesto de $140/mes con alertas al 50%/80%/100% proyectado
(`infra/bicep/modules/budget.bicep`) sigue siendo el techo común — no se
modificó en semana 2.

## 6. Acción pendiente para cerrar este entregable

1. Ejecutar el comando de §1 tras el primer despliegue real de semana 2.
2. Confirmar la elegibilidad de ambos Free Tier/Offer (Cosmos, SQL) contra
   la suscripción real — ninguno se puede confirmar desde este entorno.
3. Repetir la consulta al cierre de semana 2 y comparar contra el
   estimado de §3, igual que se dejó pendiente para semana 1.
4. Una vez exista `Azure-Semana3.md` con las decisiones de escalado,
   completar la fila de semana 3 de §5.
