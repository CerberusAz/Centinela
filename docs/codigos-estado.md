# Tabla de códigos de estado — API de ingesta

Entregable 18. Cubre los dos endpoints implementados en
`api/app/api/routes.py`.

**Decisión de diseño:** FastAPI/Starlette devuelven por defecto `422
Unprocessable Entity` para errores de validación de Pydantic. Se homologan
aquí a `400 Bad Request` (vía el manejador de excepciones en
`api/app/main.py`) porque, para esta API, todo error de validación es en
esencia "el payload no cumple el contrato" — un único código simplifica el
manejo del lado del cliente y es más convencional para errores de entrada
en APIs REST. Esta decisión queda registrada en
`docs/decisiones-arquitectura.md`.

## `POST /transactions`

| Escenario | Código | Cuerpo (resumen) |
|---|---|---|
| Payload válido, transacción nueva | `201 Created` | `{transaction_id, status: "accepted", received_at}` |
| Payload válido, `transaction_id` ya procesado (duplicado) | `200 OK` | `{transaction_id, status: "already_accepted"}` |
| Campo obligatorio ausente | `400 Bad Request` | `{error: "payload_invalido", detail: [...]}` |
| Campo con tipo incorrecto | `400 Bad Request` | ídem |
| `amount_minor_units` negativo, cero o ausente | `400 Bad Request` | ídem |
| `amount_minor_units` superior al máximo configurado | `400 Bad Request` | ídem |
| `client_timestamp` futuro (fuera de tolerancia de reloj) | `400 Bad Request` | ídem |
| `client_timestamp` sin zona horaria | `400 Bad Request` | ídem |
| `location.latitude` / `location.longitude` fuera de rango | `400 Bad Request` | ídem |
| `currency` no es un código ISO 4217 de 3 letras | `400 Bad Request` | ídem |
| Campo no contemplado en el contrato | `400 Bad Request` | ídem |
| Cuerpo no es JSON válido | `400 Bad Request` | ídem |
| Falla inesperada (p. ej. backend de almacenamiento no disponible) | `500 Internal Server Error` | `{error: "error_interno"}` — sin traza ni detalle interno; el detalle completo queda en el log del servidor |

En todos los casos `400`, `detail` es una lista de `{campo, motivo}` — información
suficiente para que el cliente corrija su payload, sin exponer rutas de
archivo, nombres de excepción de Python, ni cualquier otro detalle de
implementación.

## `GET /transactions/{transaction_id}`

| Escenario | Código | Cuerpo (resumen) |
|---|---|---|
| Transacción encontrada | `200 OK` | Documento persistido (`transaction`, `server_received_at`) |
| Transacción no encontrada | `404 Not Found` | `{error: "transaccion_no_encontrada"}` |

Este endpoint existe únicamente para satisfacer el criterio de cierre "la
transacción persistida se recupera por su identificador" (sección 4 y
criterios de aceptación de Azure-Semana1.md). No implementa consulta de
historial, cálculo de score ni ninguna lógica de análisis — solo devuelve el
documento crudo tal como se persistió.
