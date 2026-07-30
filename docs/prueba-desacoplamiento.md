# Prueba de desacoplamiento

Entregable 10. Runbook reproducible para el requisito de validación de la
sección 2.4 y los criterios de aceptación de "Desacoplamiento" (sección
4) de `Azure-Semana2.md`. **No ejecutado todavía** — requiere `az login`
y la infraestructura de semana 2 desplegada, ninguno disponible en este
entorno de desarrollo. Este documento deja los pasos y los comandos
exactos listos para ejecutar.

## Objetivo

Demostrar tres cosas:

1. La API responde a una transacción **antes** de que el motor de scoring
   termine de procesarla (marcas de tiempo).
2. Con el consumidor de casos (`cases/function_app.py`) detenido, la API
   sigue recibiendo y respondiendo transacciones con normalidad.
3. Al restablecer el consumidor, todos los casos marcados durante la
   indisponibilidad se procesan sin pérdida.

## Paso 1 — Confirmar el desacoplamiento API / motor de scoring

```bash
# Enviar una transacción y capturar la marca de tiempo de la respuesta HTTP
curl -w "\ntiempo_respuesta_api: %{time_total}s\n" -s -X POST \
  https://<web-app>.azurewebsites.net/transactions \
  -H "Content-Type: application/json" \
  -d '{ ... payload válido ... }'
```

Comparar `tiempo_respuesta_api` contra los logs de Application Insights
de la Function de scoring (`ScoringFunction`) para la misma
`transaction_id` — el timestamp de inicio de la invocación de la Function
debe ser posterior (o al menos no anterior) al momento en que la API ya
respondió. Consultar:

```bash
az monitor app-insights query \
  --app <app-insights-name> --resource-group <rg> \
  --analytics-query "traces | where message has '<transaction_id>' | project timestamp, message"
```

**Criterio de aceptación cubierto:** "La API responde a una transacción
antes de que el motor de scoring finalice su ejecución. Demostrable
mediante marcas de tiempo."

## Paso 2 — Detener el consumidor de casos

```bash
az functionapp stop --name <cases-function-app-name> --resource-group <rg>
```

Enviar varias transacciones diseñadas para activar el umbral (p. ej.
combinando velocidad + comercio de riesgo, ver `docs/umbral-scoring.md`
§3 para combinaciones que sí abren caso):

```bash
for i in 1 2 3 4 5; do
  curl -s -X POST https://<web-app>.azurewebsites.net/transactions \
    -H "Content-Type: application/json" -d '{ ... }'
done
```

Verificar que la API sigue respondiendo `201`/`200` con normalidad
(latencia comparable a la del Paso 1) — la indisponibilidad del
consumidor de casos no debe afectar la ingesta ni el scoring (el motor de
scoring solo publica en Service Bus, no espera confirmación de consumo).

Verificar que los mensajes se acumulan en la cola sin perderse:

```bash
az servicebus queue show \
  --resource-group <rg> --namespace-name <sb-namespace> --name casos-marcados \
  --query "countDetails.activeMessageCount"
```

El conteo debe reflejar los casos abiertos durante la indisponibilidad.

**Criterio de aceptación cubierto:** "Con el consumidor de casos
detenido, la API continúa recibiendo y respondiendo transacciones."

## Paso 3 — Restablecer el consumidor y verificar procesamiento sin pérdidas

```bash
az functionapp start --name <cases-function-app-name> --resource-group <rg>
```

Esperar unos minutos y verificar que el conteo de mensajes activos vuelve
a cero:

```bash
az servicebus queue show \
  --resource-group <rg> --namespace-name <sb-namespace> --name casos-marcados \
  --query "countDetails.{activos:activeMessageCount, muertos:deadLetterMessageCount}"
```

`activos` debe ser 0; `muertos` debe seguir siendo 0 (ningún mensaje
agotó `maxDeliveryCount` por error de procesamiento — si `muertos` > 0,
hay un bug en `cases/function_app.py`, no una pérdida por indisponibilidad).

Verificar en Azure SQL que existe un caso por cada transacción marcada
durante el Paso 2:

```sql
SELECT transaction_id, score, estado_codigo, fecha_apertura
FROM caso
WHERE fecha_apertura >= '<inicio del Paso 2>'
ORDER BY fecha_apertura;
```

El número de filas debe coincidir exactamente con el número de
transacciones enviadas en el Paso 2 que superaron el umbral — ni de más
(duplicados, cubierto por la idempotencia de `cases/repository.py::
create_case`) ni de menos (pérdida).

**Criterio de aceptación cubierto:** "Al restablecerse el consumidor, los
casos marcados durante la indisponibilidad se procesan sin pérdidas."

## Resultado de la ejecución

`[PENDIENTE DE EJECUCIÓN CONTRA AZURE REAL]` — completar esta sección con
los valores observados (timestamps, conteos, filas de `caso`) la primera
vez que se corra este runbook contra la infraestructura desplegada.
