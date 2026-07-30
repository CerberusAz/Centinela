# Limitación de tasa — API de ingesta

Entregable 12 de semana 2. Azure-Semana2.md, sección 2.7: "sin limitación
de tasa, un actor malicioso puede saturar la API con transacciones
sintéticas. Cada petición aceptada dispara un evento y una ejecución del
motor de scoring, con el consiguiente consumo de crédito."

## 1. Dónde se implementa y por qué ahí

La sección 2.7 aclara explícitamente que el proyecto no contempla una
capa de gestión de API dedicada (Azure API Management) — "la limitación
de tasa se implementa en la aplicación o mediante los mecanismos de
restricción disponibles en el servicio de aplicaciones." Se eligió
**aplicación** (`api/app/core/rate_limiter.py`), no un mecanismo de App
Service, porque:

- Permite responder con un código de estado semánticamente correcto
  (`429 Too Many Requests` + header `Retry-After`), en vez de que la
  conexión se corte a nivel de red — mejor experiencia para un cliente
  legítimo que se pasó del límite por error.
- Es testeable sin desplegar nada (`api/tests/test_rate_limit.py`, 6
  tests, reloj inyectable — no depende de `time.sleep()` real).
- Es portable si en el futuro se migra de App Service a otro servicio de
  cómputo: la limitación viaja con el código, no con la configuración de
  la plataforma.

## 2. Alcance: solo `POST /transactions`

La limitación se aplica únicamente al endpoint que dispara costo real
—persistencia dual + publicación de evento + ejecución del motor de
scoring— que es exactamente lo que la sección 2.7 identifica como el
riesgo ("cada petición aceptada dispara un evento y una ejecución del
motor de scoring, con el consiguiente consumo de crédito"). `GET
/transactions/{id}` y `POST /documents` no disparan ese mismo costo en
cascada y no están limitados esta semana — extenderlo a otros endpoints
es una ampliación de alcance simple si se decide necesaria (mismo
mecanismo, otro `Depends(enforce_rate_limit)`).

## 3. Valores por defecto: 60 peticiones por 60 segundos, por IP de origen

`CENTINELA_RATE_LIMIT_WINDOW_SECONDS=60`, `CENTINELA_RATE_LIMIT_MAX_REQUESTS=60`
(1 peticion/segundo sostenida en promedio, con ráfaga permitida hasta 60
dentro de la ventana).

**Por qué 60/60 y no más restrictivo:** la célula está en fase de prueba
con tráfico sintético propio (no hay integraciones reales de comercios
todavía) — un límite más agresivo (p. ej. 10/60) arriesgaría bloquear las
propias pruebas de carga legítimas del equipo durante el desarrollo.

**Por qué 60/60 y no más permisivo:** un actor malicioo enviando
transacciones sintéticas a 1 req/s sostenida durante horas ya representa
miles de ejecuciones del motor de scoring — el objetivo no es prevenir
todo abuso posible (eso requeriría un WAF/Azure Front Door, fuera de
alcance), es acotar el radio de daño de un solo origen sin coordinación
distribuida (para eso existiría un ataque DDoS real, que ninguna
limitación a nivel de aplicación resuelve por sí sola).

**Recalibración esperada:** al igual que el umbral del motor de scoring
(`docs/umbral-scoring.md`), este valor es un punto de partida razonado,
no una cifra definitiva — se ajusta por configuración
(`CENTINELA_RATE_LIMIT_*`), sin requerir cambio de código ni
redespliegue, una vez existan datos reales de tráfico legítimo.

## 4. Limitación conocida: en memoria, sin estado compartido entre instancias

El limitador (`InMemoryRateLimiter`) cuenta peticiones dentro del proceso
de una única instancia de la Web App. Con el Plan B1 sin auto-escalado
configurado esta semana, hay una sola instancia — el conteo es exacto.
Si en semana 3 se habilita auto-escalado horizontal, cada instancia
contaría de forma independiente, y el límite efectivo real sería
`max_requests × número_de_instancias` — una degradación conocida, no un
bug. Resolverlo correctamente requiere un almacén de conteo centralizado
(p. ej. Azure Cache for Redis, o tablas de la misma Storage Account ya
desplegada) — evaluar si se justifica cuando el auto-escalado sea real,
no antes.

## 5. Verificación

`api/tests/test_rate_limit.py` cubre: peticiones bajo el límite
aceptadas, la petición que excede el límite devuelve 429 con
`Retry-After`, la respuesta 429 no filtra detalles internos (mismo
criterio que las respuestas 400 de semana 1), el límite se restablece
tras pasar la ventana, orígenes distintos se cuentan de forma
independiente, y `GET /transactions/{id}` no está sujeto al límite.

**No verificado:** comportamiento real bajo carga concurrente genuina
contra la instancia desplegada, ni el escenario de múltiples instancias
descrito en §4 — ambos requieren Azure real.
