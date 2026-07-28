# Justificación del nivel de servicio de App Service

Entregable 17.

## 1. Nivel seleccionado: **Basic (B1), Linux**

Sección 2.9 exige desplegar "en el nivel de servicio más bajo que soporte la
integración con la red virtual. No se admiten niveles superiores sin
justificación de costo."

**Verificación (no asumida):** la integración regional con VNet
(`Regional VNet Integration`) requiere como mínimo el nivel **Basic**;
los niveles Free (F1) y Shared (D1) no la soportan. A partir de Basic la
integración no tiene costo adicional sobre el propio plan (Basic, Standard,
Premium v2/v3, Elastic Premium) — el costo es únicamente el del plan de
App Service.

Fuente consultada: documentación de Microsoft Learn sobre integración con
red virtual de App Service (`overview-vnet-integration`) — confirma que
Basic es el nivel mínimo elegible y que no hay cargo adicional por la
integración en sí.

Dentro de Basic, se elige el tamaño de instancia más pequeño: **B1** (1
vCPU, 1.75 GB RAM). No se justifica B2/B3: la API de esta semana solo recibe,
valida y persiste — no ejecuta lógica de scoring ni procesamiento
intensivo, y el tráfico de prueba (21 días, célula pequeña) no requiere más
cómputo.

**Por qué no Standard o superior:** Standard añade slots de despliegue,
auto-escalado y SLA superior — ninguno de estos es un requisito de la
semana 1 (no hay staging, sección 2.9 lo excluye explícitamente por
presupuesto). Se reevaluará en la semana 3 si el escalado bajo carga lo
justifica.

## 2. Costo estimado a 21 días

> **`[VERIFICAR: tarifa horaria de App Service Plan B1 Linux en la región
> finalmente seleccionada (sección 2.2, responsabilidad de Persona 1)]`**
> El precio de cómputo de Azure varía por región; el número exacto debe
> confirmarse en la calculadora de precios oficial
> (`azure.microsoft.com/pricing/calculator`) o en el portal, una vez la
> región esté decidida, y volcarse en el informe de cuotas (entregable 2).
> El cálculo de abajo usa una tarifa de ejemplo — **placeholder**, no un
> precio verificado — solo para fijar la metodología.

Metodología de cálculo:

```
costo_21_dias = tarifa_hora_B1 × horas_operativas_dia × 21 días
```

El script de apagado (entregable 5) detiene el App Service Plan al cierre
de cada jornada, por lo que el costo real depende de las horas de operación
efectivas, no de 24 h × 21 días. Ejemplo de cálculo con horario de trabajo
de célula (≈10 h/día activas):

| Variable | Valor de ejemplo (placeholder) |
|---|---|
| Tarifa B1 Linux (USD/hora) | `[VERIFICAR]` |
| Horas operativas por día | 10 |
| Días del proyecto | 21 |
| Horas totales estimadas | 210 |
| **Costo estimado (placeholder)** | `tarifa × 210` |

Este número debe reconciliarse con el **reporte de crédito consumido**
(entregable 24, responsabilidad de Persona 1) y compararse contra el límite
de 20 USD para la semana 1 fijado en los criterios de aceptación.

## 3. Riesgo de costo por inactividad

Consistente con la sección 6 ("el consumo de crédito determina la
viabilidad de la semana 3... recursos en ejecución durante periodos de
inactividad representan el principal riesgo de agotamiento"): el App
Service Plan Basic **no se factura por solicitud, se factura por tiempo de
existencia del plan** — a diferencia de un plan Consumption/serverless, un
B1 corre y cobra aunque no reciba tráfico. Esto hace que el script de
apagado (entregable 5) sea la única palanca real de ahorro para este
componente, y no la ausencia de tráfico.
