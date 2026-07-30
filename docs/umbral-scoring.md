# Justificación del umbral del motor de scoring

Parte del entregable 6 de semana 2. Valores por defecto en
`scoring/rules.py::ScoringConfig` y `scoring/config.py` (variables de
entorno `CENTINELA_SCORING_*`).

## 1. Cómo se modifica sin redespliegue

El umbral y los puntos por regla son *App Settings* de la Function App de
scoring (`infra/bicep/modules/functions.bicep`), leídos por
`scoring/config.py` (pydantic-settings) al arrancar el proceso. Cambiar un
App Setting en Azure reinicia el proceso de la Function, pero **no
requiere volver a desplegar código** — cumple literalmente el entregable
6 ("modificable sin redespliegue"). `scoring/tests/test_rules.py::
test_threshold_changes_whether_case_opens_without_changing_rule_logic`
prueba exactamente esta propiedad: mismo score, distinto umbral, distinto
resultado de apertura de caso.

## 2. Puntos por regla — severidad relativa, no aritmética arbitraria

| Regla | Puntos por defecto | Razonamiento |
|---|---|---|
| Geo-imposible | 50 | Señal más difícil de producir por error legítimo — un desplazamiento físicamente imposible casi siempre implica una tarjeta clonada o una cuenta comprometida, no una variación normal de comportamiento. |
| Monto atípico | 40 | Señal fuerte pero con más falsos positivos plausibles (un titular puede genuinamente hacer una compra grande una vez). |
| Velocidad | 30 | Un titular real puede generar varias transacciones rápidas legítimas (fila de tiendas, checkout dividido) — señal más débil aislada. |
| Comercio de riesgo | 25 | Depende de una lista curada externa; puede haber comercios legítimos mal categorizados — la señal más propensa a error de datos, no de comportamiento. |

## 3. Umbral por defecto: 100

Con estos puntos, **una sola señal aislada nunca abre caso por sí sola**
(máximo individual: 50, con `score_threshold=100`) — se requiere una
combinación de al menos dos señales, o una señal fuerte reforzada por el
contexto. Ejemplos:

- Geo-imposible (50) + monto atípico (40) = 90 → **no abre caso** (bajo el umbral).
- Geo-imposible (50) + velocidad (30) + comercio de riesgo (25) = 105 → **abre caso**.
- Monto atípico (40) + velocidad (30) + comercio de riesgo (25) = 95 → **no abre caso**.
- Geo-imposible (50) + monto atípico (40) + cualquier tercera señal → siempre abre caso.

**Por qué no un umbral más bajo (p. ej. 50):** una sola regla aislada
activaría un caso — dado que cada regla individual tiene casos de borde
legítimos documentados en `scoring/rules.py` (viajes reales, compras
grandes ocasionales, checkouts rápidos), un umbral que abre caso con una
sola señal generaría demasiados falsos positivos para el equipo de
analistas.

**Por qué no un umbral más alto (p. ej. 200):** requeriría que las 4
reglas se activaran simultáneamente (50+40+30+25=145, ni siquiera la suma
total llega a 200) — el sistema nunca abriría un caso, incumpliendo el
propósito del motor de scoring.

## 4. Trade-off explícito: falsos positivos vs. fraude no detectado

Este umbral es una decisión de negocio, no solo técnica, y se espera que
cambie con datos reales de operación (por eso es configuración, no
código). Un umbral más bajo reduce fraude no detectado a costa de más
casos falsos positivos (carga de trabajo de analistas, fricción para
titulares legítimos); un umbral más alto reduce esa carga a costa de
dejar pasar fraude con una sola señal fuerte. El valor de 100 es un punto
de partida razonado (ninguna señal aislada abre caso, cualquier
combinación de dos señales relevantes sí), sujeto a recalibración una vez
haya datos reales de la célula sobre tasas de falsos positivos.

## 5. Ventanas y umbrales de cada regla — valores por defecto

| Parámetro | Valor por defecto | Justificación breve |
|---|---|---|
| `velocity_window_seconds` | 300 (5 min) | Ventana corta acorde a "ventana temporal corta" (sección 2.3); suficiente para detectar ráfagas sin penalizar actividad normal de un día. |
| `velocity_max_count` | 5 | 5 transacciones de una cuenta en 5 minutos excede el patrón normal de un titular individual. |
| `amount_min_history_points` | 3 | Menos de 3 transacciones previas no da una línea base estadística significativa — la regla no se evalúa, no se fuerza un falso positivo sobre cuentas nuevas. |
| `amount_stddev_multiplier` | 3.0 | Regla estadística estándar (~3 desviaciones estándar) para marcar valores atípicos sin sobre-marcar variación normal. |
| `geo_max_speed_kmh` | 900.0 | Velocidad de crucero de un vuelo comercial — cualquier desplazamiento implícito mayor no es alcanzable por el mismo titular entre dos transacciones físicas. |

Todos ajustables por configuración, mismo mecanismo que el umbral
principal.
