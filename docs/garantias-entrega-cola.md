# Garantías de entrega — Cola de ingesta

Entregable 22. Describe el comportamiento del sistema en los tres escenarios
de la sección 2.11, aplicado a Azure Storage Queues (el servicio de cola
usado en Centinela).

**Cola:** `mensajes` — creada en la Storage Account `sttrialdevweu003sdfafbu4`
(módulo `infra/bicep/modules/storage.bicep`).

---

## Contexto: modelo de entrega de Azure Storage Queues

Azure Storage Queues ofrece garantía **"al menos una vez"** (_at-least-once
delivery_): un mensaje puede ser procesado más de una vez (si el consumidor
falla antes de confirmarlo), pero **nunca se pierde silenciosamente** mientras
esté dentro del tiempo de vida del mensaje (`TTL`, default: 7 días).

El mecanismo central es la **visibilidad temporal**:

1. El consumidor obtiene el mensaje (`dequeue`). El mensaje se vuelve
   **invisible** para otros consumidores durante un período configurable
   (`visibility_timeout`, default: 30 segundos).
2. Si el consumidor completa el procesamiento, **elimina** el mensaje (`delete`).
   El mensaje desaparece de la cola.
3. Si el consumidor falla o no elimina el mensaje antes de que expire el
   `visibility_timeout`, el mensaje **vuelve a ser visible** y puede ser
   procesado de nuevo por cualquier consumidor disponible.

Cada vez que el mensaje es retirado de la cola sin ser eliminado, su
contador `dequeue_count` incrementa en 1. Este contador es el mecanismo
que permite detectar mensajes envenenados.

---

## Escenario 1: Un consumidor lee un mensaje y falla antes de confirmarlo

**Descripción:** el motor de scoring (semana 2) retira un mensaje de la cola
`mensajes`, comienza a procesarlo y cae (proceso terminado, excepción no
controlada, timeout de red, reinicio de instancia).

**Comportamiento del sistema:**

1. El mensaje fue retirado con un `visibility_timeout` (p. ej. 30 s).
2. El consumidor no llama a `delete_message` antes de que expire el timeout.
3. Azure Storage Queues vuelve a hacer visible el mensaje automáticamente.
4. El siguiente consumidor disponible retira y procesa el mensaje. El
   `dequeue_count` pasa de 1 a 2.

**Garantía:** el mensaje **no se pierde**. El dato eventualmente se procesará,
posiblemente más de una vez — por eso la lógica del motor de scoring de la
semana 2 debe ser idempotente respecto al `transaction_id`.

**Consecuencia de diseño para la semana 2:** el motor de scoring debe consultar
si ya procesó el `transaction_id` antes de volver a calcular el score. Esto es
coherente con la estrategia de idempotencia documentada en `docs/idempotencia.md`.

---

## Escenario 2: Un mensaje falla de forma reiterada en su procesamiento

**Descripción:** el motor de scoring retira el mismo mensaje en múltiples
oportunidades y falla en cada intento. El `dequeue_count` crece con cada
reintento fallido.

**Política de mensajes envenenados (_poison message policy_):**

Azure Storage Queues **no tiene dead-letter nativo** (a diferencia de
Azure Service Bus). La política debe implementarse en el consumidor:

| Paso | Acción |
|---|---|
| `dequeue_count` ≤ 4 | El consumidor reintenta el procesamiento normalmente |
| `dequeue_count` = 5 | El consumidor detecta el umbral, copia el mensaje a la cola auxiliar `mensajes-poison`, y lo elimina de `mensajes` |
| Cola `mensajes-poison` | Monitorizada por alerta de Azure Monitor; requiere intervención manual del equipo de operaciones |

**Justificación del umbral de 5:** tres reintentos podrían ser insuficientes
para errores transitorios de red; diez retradarían demasiado el diagnóstico.
Cinco reintentos con un backoff progresivo cubren el 99% de los errores
transitorios esperados en un entorno cloud (timeouts de red, reinicio de
instancia, throttling momentáneo).

**Nota de implementación:** la cola `mensajes-poison` también se crea como
recurso de infraestructura en `infra/bicep/modules/storage.bicep` (pendiente
de agregar en la siguiente iteración del script). La lógica de detección y
movimiento vive en el consumidor (semana 2), no en la API de ingesta.

**Riesgo documentado:** si el `visibility_timeout` es muy corto (< tiempo de
procesamiento normal), mensajes válidos pueden incrementar `dequeue_count` sin
que haya un error real. El `visibility_timeout` debe calibrarse contra el
tiempo promedio de procesamiento del motor de scoring.

---

## Escenario 3: La cola crece a mayor velocidad de la que se vacía

**Descripción:** la tasa de ingreso de transacciones supera la capacidad del
motor de scoring para consumirlas. La profundidad de la cola (`ApproximateMessageCount`)
crece de forma sostenida.

**Comportamiento del sistema:**

| Capa | Comportamiento |
|---|---|
| **API de ingesta** | Sigue aceptando transacciones y publicando mensajes sin degradación. La cola no genera back-pressure sobre la API. |
| **Motor de scoring** | Procesa los mensajes en orden FIFO con retraso creciente. Las transacciones se analizan eventualmente, pero fuera del tiempo real. |
| **Limite de capacidad de la cola** | Azure Storage Queues soporta hasta **500 TB** de mensajes. El límite práctico es el TTL de los mensajes (7 días por defecto): un mensaje no procesado en 7 días expira y se elimina automáticamente. |

**Riesgos concretos:**

1. **Latencia de detección:** si la cola se acumula por horas, el motor de
   scoring detectará patrones fraudulentos con retraso, reduciendo la efectividad
   de las reglas de velocidad y geo-imposible.
2. **Expiración de mensajes:** si la acumulación dura más de 7 días (el TTL),
   los mensajes más antiguos expiran sin ser procesados. Esto implica
   transacciones sin score calculado.

**Respuesta operativa:**

| Señal | Acción |
|---|---|
| `ApproximateMessageCount` > 1000 | Alerta en Azure Monitor |
| `ApproximateMessageCount` > 5000 | Escalar instancias del motor de scoring (semana 3) |
| Mensajes acumulados > 1 día | Revisar si el TTL de 7 días es suficiente o ampliarlo hasta 14 días |

**Nota para la semana 3:** el escalado del motor de scoring bajo carga es el
mecanismo principal para vaciar la cola ante picos de tráfico. La API de ingesta
no debe modificarse para gestionar la profundidad de la cola — esa
responsabilidad es del consumidor y de las reglas de escalado automático.
