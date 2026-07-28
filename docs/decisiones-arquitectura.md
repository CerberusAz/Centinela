# Documento de decisiones de arquitectura

Entregable 25. Acompaña las tres semanas del proyecto Centinela. Se
registra aquí toda decisión de arquitectura no trivial, con su alternativa
descartada y la razón. Formato ADR simplificado: Contexto / Decisión /
Alternativas descartadas / Consecuencias.

Este documento lo inicia Persona 4 con las decisiones de su alcance
(contrato, API, idempotencia, nivel de servicio). Las secciones marcadas
como `[PENDIENTE — Persona N]` deben completarlas las personas 1, 2 y 3 con
sus propias decisiones (región y costo, identidad, red/almacenamiento/cola).

---

## ADR-001 — Persistencia de la transacción cruda en Blob Storage (semana 1)

**Contexto:** la sección 2.9 exige persistir la transacción cruda al
recibirla, pero los almacenes relacional y documental no se despliegan
hasta la semana 2 (sección 1, "fuera de alcance"). Se necesita un destino
de persistencia disponible desde el día 1.

**Decisión:** cada transacción se persiste como un blob JSON individual en
un contenedor `raw-transactions`, usando `transaction_id` como nombre de
blob.

**Alternativas descartadas:** persistencia en archivo local del App
Service (no sobrevive reinicios/escalado, y App Service en Linux no
garantiza almacenamiento persistente entre instancias); adelantar el
despliegue de una base de datos a la semana 1 (fuera del alcance
explícito de la semana, sección 1).

**Consecuencias:** en la semana 2, cuando se despliegue el almacén
definitivo, el punto de persistencia (`app/storage/ports.py`) ya está
abstraído detrás de una interfaz — agregar un backend relacional/documental
es una nueva implementación de `TransactionStorage`, seleccionable por
configuración (`app/storage/factory.py`), sin tocar la capa de servicio ni
el endpoint.

## ADR-002 — Identificador de transacción generado por el cliente de origen

Ver justificación completa en `docs/contrato-transaccion.md` §2.4.
Consecuencia directa: la estrategia de idempotencia (`docs/idempotencia.md`)
depende de que el origen no reutilice un `transaction_id` para dos
transacciones distintas.

## ADR-003 — Timestamp dual: `client_timestamp` informativo, `server_received_at` autoritativo

Ver justificación completa en `docs/contrato-transaccion.md` §2.1.

## ADR-004 — Monto como entero en unidad menor + ISO 4217, sin coma flotante

Ver justificación completa en `docs/contrato-transaccion.md` §2.2.

## ADR-005 — Política de campos no contemplados: rechazo estricto

Ver justificación completa en `docs/contrato-transaccion.md` §2.5.

## ADR-006 — Homologación de errores de validación a HTTP 400

**Contexto:** FastAPI devuelve `422` por defecto para errores de Pydantic.

**Decisión:** todo error de incumplimiento del contrato (forma o
semántica) responde `400 Bad Request`.

**Alternativas descartadas:** mantener `422` para errores de forma y `400`
para errores semánticos (dos códigos para la misma categoría de problema —
"tu payload no es válido" — añade una distinción que el cliente de la API
no necesita).

**Consecuencias:** documentado en `docs/codigos-estado.md`. Cualquier
consumidor de la API debe tratar `400` como "corrige el payload y
reintenta", nunca como error transitorio.

## ADR-007 — Nivel de servicio App Service: Basic B1

Ver justificación completa en `docs/nivel-servicio-costo.md`.

## ADR-008 — Punto de inserción de mensajería: tras persistir, antes de responder

**Contexto:** la sección 2.9 exige que el código esté estructurado en capas
de modo que agregar la publicación de eventos en la semana 2 no requiera
reescribir el endpoint.

**Decisión:** `IngestionService.ingest()` invoca un `EventPublisher`
(interfaz) inmediatamente después de persistir y antes de retornar. La
semana 1 usa `NoOpEventPublisher`; la semana 2 activa el publisher real
cambiando `CENTINELA_EVENT_PUBLISHER_BACKEND` por configuración.

**Consecuencias:** el endpoint (`app/api/routes.py`) y la firma de
`IngestionService.ingest()` no cambian en la semana 2.

---

## `[PENDIENTE — Persona 1]` Suscripción, costo y región

_Decisiones sobre: límite de gasto, alertas de presupuesto, región
seleccionada y su justificación, convención de nombres aplicada en el
script de aprovisionamiento._

## `[PENDIENTE — Persona 2]` Identidad y control de acceso

_Decisiones sobre: diseño de la matriz de roles y permisos, alcance exacto
de la identidad gestionada del rol Servicio, resultado de las pruebas
negativas._

## `[PENDIENTE — Persona 3]` Red, almacenamiento y cola

_Decisiones sobre: topología de subredes y dimensionamiento, mecanismo de
restricción de acceso por subred elegido (y por qué no el equivalente de
pago), política de mensajes fallidos de la cola, nivel de redundancia y
ciclo de vida del contenedor de documentos de identidad._
