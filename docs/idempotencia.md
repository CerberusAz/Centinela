# Estrategia de idempotencia

Entregable 23. La implementación (parcial, sobre almacenamiento en
memoria/Blob) ya existe en `api/app/services/ingestion.py` y
`api/app/storage/`; este documento explica el razonamiento, tal como exige
la sección 2.12. Complementa `docs/contrato-transaccion.md` §2.4
(identificador).

## 1. Clave de idempotencia

`transaction_id`, generado por el sistema de origen (no por el servidor).
Justificación completa en `docs/contrato-transaccion.md` §2.4.

## 2. ¿En qué punto es seguro confirmar la aceptación al cliente?

La secuencia es recibir → validar → persistir → responder (sección 2.9).
**El punto seguro es después de que la persistencia se confirme
exitosamente, inmediatamente antes de responder** — nunca antes.

**Por qué no antes:** si la API confirmara la aceptación (p. ej. respondería
`200`) antes de persistir, y el proceso fallara entre ese instante y la
escritura real (caída del proceso, error del backend de almacenamiento), el
cliente creería que la transacción fue aceptada cuando en realidad no existe
ningún registro de ella. Para un sistema financiero esa inconsistencia es
inaceptable: es indistinguible de "perder" una transacción.

**Por qué no después de un paso adicional (p. ej. tras publicar el evento a
la cola):** la publicación del evento hacia el motor de scoring (semana 2)
es un paso *posterior* a la persistencia y no debe bloquear el acuse al
cliente de origen — la API de ingesta no debe acoplar su disponibilidad a la
disponibilidad del motor de scoring asíncrono (sección 2.9: "la API no
debe... calcular scores... el análisis es responsabilidad del motor de
scoring, que opera de forma asíncrona"). Confirmar tan pronto como el dato
está persistido de forma durable es el punto que minimiza la ventana de
inconsistencia sin acoplar componentes que deben permanecer desacoplados.

## 3. Comportamiento ante una transacción duplicada

1. La API recibe una transacción con un `transaction_id` ya persistido
   anteriormente (reintento del cliente, red inestable, timeout del acuse
   original, etc.).
2. Antes de persistir, `IngestionService.ingest()` consulta
   `storage.exists(transaction_id)`.
3. Si ya existe: **no se vuelve a persistir, no se vuelve a publicar el
   evento hacia el motor de scoring**, y se responde `200 OK` con
   `{transaction_id, status: "already_accepted"}` — un acuse, no un error:
   desde la perspectiva del cliente, su transacción fue aceptada
   (posiblemente en un intento anterior) y no necesita reintentar de nuevo.

Esto evita dos problemas concretos: (a) transacciones duplicadas en los
almacenes de la semana 2, que distorsionarían el cálculo de score (p. ej.
una regla de velocidad contaría la misma transacción dos veces), y (b) doble
publicación de eventos, que haría que el motor de scoring procese la misma
transacción más de una vez.

## 4. Condición de carrera conocida

`exists()` y `save()` son dos operaciones separadas. Si dos requests
concurrentes con el mismo `transaction_id` llegan casi simultáneamente,
ambas pueden observar `exists() == False` antes de que cualquiera termine de
persistir.

**Mitigación en el backend de Blob Storage:** `BlobTransactionStorage.save()`
usa escritura condicional (`upload_blob(..., overwrite=False)`). Si dos
escrituras compiten por el mismo nombre de blob, solo una prospera; la
segunda recibe `ResourceExistsError`, que se captura y se ignora
silenciosamente — el dato ya quedó persistido por la primera.

**Limitación conocida, aceptada para esta semana:** en ese escenario de
carrera, ambas respuestas HTTP pueden ser `201 Created` (porque ambas
pasaron el chequeo `exists()` antes de intentar escribir), aunque solo una
escritura fue efectiva. El dato final es correcto (una sola copia
persistida, sin duplicados) pero el código de respuesta de la "perdedora" de
la carrera no refleja con exactitud que su escritura fue un no-op. No se
implementa un lock distribuido ni una transacción condicional de
lectura-antes-de-escribir atómica esta semana: el impacto es cosmético (un
`201` en vez de `200` en una ventana de milisegundos, en un escenario de
concurrencia real, poco frecuente para tráfico de un solo origen por
`account_id`). Se revisará si el volumen de la semana 3 lo justifica.

## 5. Expiración de la clave de idempotencia

No se define TTL ni purga esta semana: cada `transaction_id` es único de
forma indefinida dentro del contenedor `raw-transactions`. La política de
ciclo de vida del contenedor (retención, transición a niveles de acceso más
fríos) es responsabilidad de la sección 2.10 / Persona 3 y no afecta la
semántica de idempotencia mientras el blob exista.
