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

De `README.md` §Análisis de Costos:

| Componente | Estimado | Riesgo |
|---|---|---|
| Cosmos DB (Free Tier) | $0.00 | Elegibilidad no verificada — uno por suscripción |
| Azure SQL (Serverless GP, Free Offer) | ~$0.00 | Elegibilidad no verificada; fallback Basic ~$5/mes si no aplica |
| Event Grid | Centavos | Pay-per-operation, volumen de prueba |
| Service Bus (Basic) | Centavos | Pay-per-operation, sin costo base |
| 2 Function Apps (Consumption) | ~$0.00 | Dentro de la capa gratuita mensual de ejecuciones |
| Storage Account de runtime (Functions) | ~$0.10 | LRS, mínimo tráfico |
| **Total estimado, componentes nuevos** | **Unos pocos USD** | Depende críticamente de que ambos Free Tier/Offer apliquen |

Sumado al estimado de semana 1 (~$10-$14, `docs/reporte-credito-consumido.md`
§3), el estimado acumulado de referencia (no verificado) queda **bien por
debajo de $40**, pero con más riesgo de desviación que semana 1: dos
Free Tier/Offer distintos deben ambos aplicar para que el estimado se
sostenga. Si cualquiera de los dos no aplica, revisar el fallback
documentado en cada caso (`docs/justificacion-particionamiento-cosmos.md`
§4, `docs/estrategia-respaldo-sql.md` — la elegibilidad del Free Offer se
verifica junto con el resto de la instancia real).

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
