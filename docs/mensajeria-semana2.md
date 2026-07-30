# Mensajería de semana 2 — Event Grid vs. Service Bus

Entregable 8. Azure-Semana2.md, sección 2.4, exige dos mecanismos de
mensajería con propósito distinto y la diferencia entre ambos documentada
explícitamente.

## 1. Los dos mecanismos y por qué son servicios distintos, no config distinta del mismo servicio

| | Distribución del evento de transacción | Cola de casos marcados |
|---|---|---|
| **Servicio** | Event Grid (topic personalizado `evt-...`) | Service Bus (tier Basic, cola `casos-marcados`) |
| **Quién publica** | `api/app/messaging/event_grid_publisher.py` (Web App) | `scoring/servicebus_publisher.py` (Function de scoring) |
| **Quién consume** | `scoring/function_app.py` (Function de scoring, trigger de Event Grid) | `cases/function_app.py` (Function de casos, trigger de Service Bus) |
| **Propósito** | Notificar la ocurrencia de un evento | Garantizar el procesamiento |
| **Garantía de entrega** | Reintentos con backoff exponencial, expira (~24h por defecto) si nadie confirma | At-least-once, con dead-lettering NATIVO (`maxDeliveryCount`) |
| **¿Hay cola persistente consultable?** | No — es pub/sub, no hay "profundidad de cola" que inspeccionar | Sí — `ApproximateMessageCount`, mensajes visibles hasta ser completados |
| **Autenticación** | AAD, rol "EventGrid Data Sender" (sin la clave del topic) | AAD, roles "Azure Service Bus Data Sender/Receiver" (`disableLocalAuth: true`, sin connection string con clave compartida) |
| **Restricción de red** | Ninguna — Event Grid no soporta Service Endpoints de VNet | Service Endpoint restringido a `snet-scoring` (defensa en profundidad, además del AAD-only) |

## 2. Por qué esta asignación y no la inversa

**El evento de transacción es "dispara y olvida" por diseño explícito de
la sección 2.4:** "La API publica un evento tras persistir la transacción
y finaliza su ejecución... La API no conoce ni espera el resultado del
scoring." Esto es exactamente el modelo de Event Grid: notificar que algo
ocurrió, sin que el productor necesite saber si/cuándo se procesó. Si el
motor de scoring está caído, el evento se reintenta durante un tiempo
acotado y luego se descarta — aceptable, porque el sistema no promete que
toda transacción se puntúe en tiempo real bajo cualquier falla; promete
que la ingesta nunca se bloquea por el scoring.

**El caso marcado NO puede perderse — por eso Service Bus, no Event
Grid.** La sección 2.4 es explícita: "debe garantizar que ningún caso se
pierda ante la indisponibilidad del consumidor." Un caso de fraude
detectado es la salida de valor del sistema — perder uno silenciosamente
(porque el consumidor estuvo caído más de ~24h, o por cualquier fallo
transitorio sin reintento persistente) es inaceptable. Service Bus da
entrega garantizada con reintentos ilimitados hasta `maxDeliveryCount`, y
tras agotarlos, el mensaje va a una dead-letter queue nativa — nunca
desaparece sin dejar rastro.

**Relación con la política manual de semana 1
(`docs/garantias-entrega-cola.md`).** Esa política (mover a
`mensajes-poison` tras 5 intentos, contando `dequeue_count` a mano) se
diseñó sobre Storage Queue porque en semana 1 no existía todavía la
distinción formal entre "notificar" y "garantizar" — solo había una cola
genérica. Semana 2 formaliza esa distinción con dos servicios
purpose-built: Service Bus resuelve nativamente lo que la política manual
de semana 1 tuvo que implementar a mano en el consumidor. Las colas
`mensajes`/`mensajes-poison` de Storage Queue quedan sin uso real en el
flujo de producción (ver nota de corrección al inicio de
`docs/garantias-entrega-cola.md`).

## 3. Notificar vs. garantizar — la distinción conceptual

**Notificar la ocurrencia de un evento** significa: el productor informa
que algo pasó, en el mejor esfuerzo, sin comprometerse a que el mensaje
sobreviva indefinidamente ni a que exista un único consumidor
responsable. Es el modelo correcto cuando la ausencia de procesamiento de
un evento individual es tolerable (aquí: si una transacción
excepcionalmente no llega a puntuarse por una falla prolongada del motor
de scoring, es una degradación del sistema de detección, no una pérdida
de datos financieros — la transacción cruda ya está persistida en Blob y
Cosmos, sin depender del evento).

**Garantizar el procesamiento** significa: el sistema se compromete a que
todo mensaje aceptado eventualmente será procesado exactamente una vez
como mínimo (at-least-once), incluso si el consumidor está caído por
horas — el mensaje espera en la cola. Es el modelo correcto cuando la
pérdida es inaceptable: un caso de fraude no detectado por pérdida de
mensaje es, por definición, el escenario que todo el sistema existe para
evitar.

## 4. Requisito de validación (entregable 10)

Con el consumidor de casos (`cases/function_app.py`) detenido, la API
debe seguir aceptando y respondiendo transacciones con normalidad, y al
restablecer el consumidor, todos los casos marcados durante la
indisponibilidad deben procesarse sin pérdida. Runbook reproducible en
`docs/prueba-desacoplamiento.md` — no ejecutado todavía contra Azure real
(requiere `az login` y los recursos desplegados).
