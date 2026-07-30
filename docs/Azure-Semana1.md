# Centinela — Semana 1

## Fundamentos de infraestructura e ingesta

## 1. Alcance de la semana

Esta semana se construye la base sobre la que operarán las semanas 2 y 3: la suscripción y sus controles de costo, la infraestructura aprovisionada por script, el modelo de identidades y permisos, la red privada, la API de ingesta de transacciones y los almacenes de objetos y mensajes.

Al cierre de la semana el sistema debe recibir transacciones, validarlas y persistirlas. **No se implementa ninguna lógica de detección de fraude.** El motor de scoring corresponde a la semana 2.

**Fuera del alcance de esta semana:** reglas de detección, cálculo de score, apertura de casos, bases de datos relacionales o documentales, mensajería de eventos, servicios de inteligencia artificial.



## 2. Requerimientos

### 2.1 Suscripción y control de costo

La célula opera sobre una suscripción gratuita de Azure con crédito limitado y vigencia de 30 días. El proyecto tiene una duración de 21 días.

**Requerimientos:**

- La suscripción se crea el primer día del proyecto. Una cuenta creada con anterioridad no es válida: su vigencia ya está corriendo.
- Verificar que el límite de gasto de la suscripción esté activo y documentar su comportamiento al agotarse el crédito.
- Configurar alertas de presupuesto con umbrales definidos y justificados.
- Elaborar un **informe de cuotas** de la suscripción. El crédito disponible y la cuota asignada son controles independientes: un servicio puede tener cuota cero aunque exista saldo. El informe debe consignar, como mínimo:
  - Capacidad de cómputo disponible.
  - Disponibilidad y nivel del servicio de reconocimiento documental en la región seleccionada.
  - Servicios que presentan cuota cero.

El informe de cuotas condiciona el diseño de las semanas 2 y 3. Debe completarse antes de comprometer decisiones de arquitectura.

### 2.2 Región

Seleccionar la región de despliegue y justificar la decisión considerando latencia, disponibilidad de los servicios requeridos en las semanas 2 y 3 (verificada, no asumida) y costo.

### 2.3 Infraestructura como código

Toda la infraestructura se aprovisiona mediante un script versionado en el repositorio, ejecutado con la interfaz de línea de comandos de la plataforma.

**Requerimientos del script:**

- Ejecutable sobre una suscripción vacía sin intervención manual.
- Parametrizado: los valores variables (nombres, región, tamaños) se declaran al inicio, no se repiten en el cuerpo.
- Idempotente en la medida en que los comandos lo permitan. Documentar los casos en que no sea posible.
- Emite salida informativa al finalizar.

Se requiere adicionalmente un **script de apagado** que detenga o elimine los recursos que consumen crédito. Se ejecuta al cierre de cada jornada.

### 2.4 Convención de nombres

Definir y documentar una convención de nombres para los recursos. Debe contemplar proyecto, tipo de recurso y ambiente, y resolver el caso de los recursos cuyo nombre debe ser único globalmente.

### 2.5 Clasificación de componentes

Identificar cada componente previsto del sistema a partir del recorrido de una transacción descrito en el documento de alcance. Para cada uno, determinar el modelo de servicio de nube bajo el que opera y la distribución de responsabilidades entre la célula y el proveedor.

### 2.6 Identidad y control de acceso

Se definen cuatro roles: Analista de fraude, Administrador, Servicio y Auditor de solo lectura.

**Requerimientos:**

- Derivar los permisos de cada rol a partir de sus funciones de negocio, aplicando el principio de menor privilegio.
- Distinguir explícitamente entre permisos de plano de control (administrar el recurso) y de plano de datos (operar sobre su contenido). Los roles integrados de la plataforma con frecuencia combinan ambos; revisar las acciones que incluyen antes de asignarlos.
- El rol Servicio debe autenticarse mediante **identidad gestionada por la plataforma**, sin credenciales administradas por la célula.
- Cada permiso otorgado al rol Servicio debe tener asociada la operación concreta del sistema que lo requiere. Un permiso sin operación asociada se retira.
- Las asignaciones de rol se crean desde el script de aprovisionamiento.

**Validación:** ejecutar como mínimo tres pruebas de acceso negativas y registrar sus resultados:

| Rol | Acción intentada | Resultado esperado |
|---|---|---|
| Analista | Modificar configuración de un recurso de infraestructura | Denegado |
| Auditor | Modificar cualquier recurso | Denegado |
| Servicio | Crear un recurso nuevo | Denegado |

**Documentación conceptual:** describir, aplicado a Centinela, dónde ocurre la autenticación y dónde la autorización, con un ejemplo concreto de cada una.

### 2.7 Red privada

**Requerimiento no negociable:** los almacenes de datos no deben ser alcanzables desde internet. Únicamente la subred de aplicación puede acceder a ellos.

Los almacenes relacionales y documentales se despliegan en la semana 2, pero la red se diseña esta semana bajo esa restricción.

**Requerimientos:**

- Definir la topología: subredes, rangos de direcciones y componentes asignados a cada una, incluyendo los previstos para las semanas 2 y 3.
- Dimensionar los rangos considerando el escalado de la semana 3. La integración de la aplicación con la red virtual requiere una subred dedicada; verificar su tamaño mínimo.
- Aplicar reglas de tráfico bajo el criterio de denegar por defecto. Cada regla debe especificar origen, destino, puerto y la operación del sistema que la justifica. No se admiten reglas que permitan tráfico desde cualquier origen.
- Aislar la capa de datos mediante el mecanismo de restricción de acceso por subred que ofrece la plataforma sin costo adicional. Documentar sus diferencias respecto al mecanismo equivalente de pago.
- Demostrar el aislamiento intentando alcanzar la cuenta de almacenamiento desde fuera de la red.

### 2.8 Contrato de la transacción

El contrato de la transacción es la estructura de datos que atraviesa todo el sistema. Se define esta semana y su modificación posterior implica intervenir la API, el motor de scoring, la mensajería y los almacenes simultáneamente.

El contrato debe permitir responder, sobre cualquier transacción, las preguntas que requieren las reglas de detección de la semana 2:

| Pregunta | Regla que la requiere |
|---|---|
| ¿De qué cuenta proviene? | Velocidad, monto atípico |
| ¿Cuál es el monto? | Monto atípico |
| ¿En qué instante exacto ocurrió? | Velocidad, geo-imposible |
| ¿Desde qué ubicación se originó? | Geo-imposible |
| ¿Hacia qué comercio o categoría se dirige? | Comercio de riesgo |
| ¿Cómo se identifica de forma única? | Trazabilidad, idempotencia |

**Decisiones que deben resolverse y justificarse explícitamente:**

- **Marca de tiempo.** Zona horaria y origen del valor. Si se acepta la marca de tiempo enviada por el cliente, un actor malicioso puede manipular la regla de velocidad.
- **Monto.** Tipo de dato y tratamiento de la moneda. Evaluar las implicaciones de utilizar punto flotante para valores monetarios.
- **Ubicación.** Representación que permita el cálculo de distancias requerido por la regla geo-imposible.
- **Identificador.** Origen del valor y comportamiento del sistema ante identificadores repetidos.

### 2.9 API de ingesta

Desplegar la API de transacciones en el servicio de aplicaciones, en el nivel de servicio más bajo que soporte la integración con la red virtual. No se admiten niveles superiores sin justificación de costo.

**Comportamiento requerido, en orden:**

1. Recibir el payload.
2. Validar el cumplimiento del contrato.
3. Persistir la transacción cruda.
4. Responder con acuse de recibo.

**La API no debe** consultar historial, calcular scores, aplicar reglas ni abrir casos. Este comportamiento no se implementa en esta semana ni en las siguientes: el análisis es responsabilidad del motor de scoring, que opera de forma asíncrona.

**Validación de entrada.** Rechazar, con código de estado correcto y mensaje que no exponga información interna del sistema:

- Campos obligatorios ausentes o de tipo incorrecto.
- Montos negativos, nulos o fuera de un rango razonable.
- Marcas de tiempo futuras.
- Coordenadas fuera de rango.
- Campos no contemplados en el contrato. La política aplicada a este caso se define en la célula y se registra.

**Configuración.** Externalizada respecto al código, gestionada mediante la configuración de la aplicación. El proyecto no contempla entornos de staging con intercambio de despliegue: el nivel de servicio requerido excede el presupuesto. La configuración debe estructurarse de modo que su incorporación posterior no implique cambios de código.

**Preparación para la mensajería.** En la semana 2 la API publicará un evento tras persistir la transacción. El código debe estructurarse en capas de modo que la incorporación de la publicación no requiera reescribir el endpoint. Identificar explícitamente el punto de inserción.

### 2.10 Almacenamiento de objetos

Contenedor destinado a los documentos de verificación de identidad que los analistas cargan al escalar un caso.

**Requerimientos:**

- **Nivel de acceso privado.** El acceso de los analistas se resuelve mediante un mecanismo de acceso temporal y delegado. No se admite exponer el contenedor públicamente.
- **Nivel de redundancia.** Seleccionar el más económico que satisfaga el requisito de preservación de evidencia. Justificar.
- **Política de ciclo de vida.** Definir transiciones y, si aplica, eliminación. Considerar requisitos de retención propios de un sistema financiero.
- **Convención de nombres** que relacione cada documento con su caso y evite colisiones.

**Carga desde la API:**

- Autenticación mediante identidad gestionada. No se admiten claves de acceso ni cadenas de conexión con credenciales embebidas.
- Validación de tipo de archivo por contenido real, no por extensión.
- Límite de tamaño máximo.
- El nombre del objeto en destino lo genera el sistema. No se utiliza el nombre de archivo proporcionado por el usuario.

### 2.11 Cola de ingesta

Cola destinada a absorber ráfagas de transacciones cuando la tasa de ingreso supera la capacidad de procesamiento.

**Requerimientos:**

- Cola creada, con escritura y lectura validadas.
- Política de mensajes fallidos definida y justificada.
- Documentar el comportamiento del sistema en tres escenarios:
  - Un consumidor lee un mensaje y falla antes de confirmarlo.
  - Un mensaje falla de forma reiterada en su procesamiento.
  - La cola crece a mayor velocidad de la que se vacía.

### 2.12 Estrategia de idempotencia

Determinar en qué punto de la secuencia recibir–validar–persistir–responder es seguro confirmar la aceptación de la transacción al cliente, y documentar el comportamiento del sistema ante la recepción duplicada de una misma transacción.

La implementación es opcional en esta semana. La estrategia escrita es obligatoria.



## 3. Entregables

| # | Entregable | Descripción |
|---|---|---|
| 1 | Suscripción operativa | Con límite de gasto verificado y alertas de presupuesto configuradas. |
| 2 | Informe de cuotas | Disponibilidad, cuotas en cero y verificación del servicio de reconocimiento documental en la región seleccionada. |
| 3 | Justificación de región | Documento escrito. |
| 4 | Script de aprovisionamiento | Versionado, parametrizado, idempotente, con salida informativa. |
| 5 | Script de apagado | Ejecutable al cierre de cada jornada. |
| 6 | Convención de nombres | Con ejemplos y resolución del caso de unicidad global. |
| 7 | Tabla de clasificación de componentes | Modelo de servicio y distribución de responsabilidades. |
| 8 | Matriz de roles y permisos | Cada permiso con la operación del sistema que lo justifica. |
| 9 | Identidad gestionada configurada | Para el rol Servicio, documentada. |
| 10 | Bitácora de pruebas negativas | Tres pruebas, con resultados y evidencia. |
| 11 | Nota de autenticación vs. autorización | Aplicada a Centinela, con ejemplos. |
| 12 | Diagrama de red | Subredes, rangos, componentes actuales y futuros, reglas de tráfico. |
| 13 | Tabla de reglas de tráfico | Origen, destino, puerto, justificación operativa. |
| 14 | Prueba de aislamiento | Evidencia de que la capa de datos no es alcanzable desde internet. |
| 15 | Contrato de la transacción | Campos, tipos, obligatoriedad, formato y propósito. Con las cuatro decisiones explícitas resueltas. |
| 16 | API de ingesta desplegada | Dentro de la red, con validación completa y configuración externalizada. |
| 17 | Justificación del nivel de servicio | Incluyendo costo estimado para 21 días. |
| 18 | Tabla de códigos de estado | Escenario y código devuelto. |
| 19 | Contenedor de objetos configurado | Con acceso delegado, redundancia, ciclo de vida y convención de nombres. |
| 20 | Carga de documentos operativa | Con identidad gestionada y validaciones. |
| 21 | Cola creada y validada | Con política de mensajes fallidos. |
| 22 | Documento de garantías de entrega | Los tres escenarios descritos en 2.11. |
| 23 | Estrategia de idempotencia | Documento escrito. |
| 24 | Reporte de crédito consumido | Con proyección a tres semanas. |
| 25 | Documento de decisiones de arquitectura | Iniciado. Acompaña las tres semanas. |
| 26 | README de despliegue | Permite a un tercero clonar el repositorio y levantar el sistema. |

---

## 4. Validación de cierre

Antes de dar la semana por concluida, ejecutar la siguiente secuencia y registrar los resultados:

1. Eliminar el grupo de recursos completo.
2. Ejecutar el script de aprovisionamiento sobre la suscripción vacía.
3. Completar la configuración siguiendo exclusivamente el README.
4. Enviar una transacción válida y verificar su persistencia.
5. Enviar una transacción inválida y verificar el rechazo.
6. Cargar un documento y verificar su llegada al contenedor.
7. Escribir y leer un mensaje de la cola.
8. Intentar alcanzar el almacenamiento desde internet y verificar el bloqueo.
9. Consultar y registrar el crédito consumido.
10. Ejecutar el script de apagado.

Cualquier paso que requiera conocimiento no documentado indica trabajo pendiente.



## 5. Criterios de aceptación

**Infraestructura y costo**

- [ ] La suscripción se creó el primer día del proyecto y su vigencia cubre los 21 días con margen.
- [ ] El script se ejecuta sobre una suscripción vacía sin errores y una segunda ejecución no produce efectos adversos.
- [ ] Ningún nombre de recurso está escrito directamente en el cuerpo del script.
- [ ] La región seleccionada dispone de todos los servicios previstos para las semanas 2 y 3, verificado documentalmente.
- [ ] El crédito consumido durante la semana 1 es inferior a 20 USD.
- [ ] El script de apagado se ejecutó al cierre de cada jornada.

**Identidad**

- [ ] Cada permiso de la matriz tiene asociada una operación del sistema.
- [ ] El rol Auditor no puede modificar ningún recurso. Verificado por prueba.
- [ ] El rol Analista no puede modificar configuración de infraestructura. Verificado por prueba.
- [ ] El rol Servicio no administra credenciales generadas por la célula.
- [ ] Las asignaciones de rol se recrean ejecutando el script.

**Red**

- [ ] La red se recrea ejecutando el script.
- [ ] Cada regla de tráfico cuenta con justificación operativa escrita.
- [ ] No existe ninguna regla que permita tráfico desde cualquier origen.
- [ ] El intento de alcanzar la capa de datos desde internet falla. Demostrado.
- [ ] La subred de aplicación cumple el tamaño mínimo requerido para la integración de red.

**Ingesta**

- [ ] La API responde a una transacción válida sin ejecutar lógica de análisis.
- [ ] La API rechaza cada tipo de payload inválido con el código correcto, sin exponer información interna.
- [ ] La transacción persistida se recupera por su identificador.
- [ ] El nivel de servicio seleccionado es el mínimo que satisface los requisitos, con costo justificado.
- [ ] El contrato permite responder las seis preguntas requeridas por las reglas de detección.

**Almacenamiento**

- [ ] El contenedor no es accesible públicamente. Verificado sin credenciales.
- [ ] El acceso de un analista a un documento se realiza mediante un mecanismo temporal.
- [ ] La carga de documentos utiliza identidad gestionada, sin claves.
- [ ] Un archivo con extensión falsificada es rechazado.
- [ ] Un archivo que excede el tamaño máximo es rechazado.
- [ ] El nombre del objeto en destino no corresponde al proporcionado por el usuario.
- [ ] La cola acepta escritura y lectura, y cuenta con política de mensajes fallidos.

**Transversal**

- [ ] No existe ninguna credencial en el código, en el repositorio ni en el historial de control de versiones.
- [ ] La infraestructura completa se reconstruye siguiendo el README.



## 6. Consideraciones técnicas

**El diseño de red es la decisión de mayor costo de reversión.** Los almacenes de la semana 2 se despliegan sobre esta red. Corregir el aislamiento con el pipeline en operación y datos persistidos es considerablemente más costoso que definirlo ahora.

**Los permisos amplios no se restringen retroactivamente.** Un rol Servicio con permisos excesivos funcionará correctamente en la semana 2, lo que impide detectar el exceso. La restricción debe aplicarse antes de que existan componentes que dependan de él.

**El contrato de la transacción es un compromiso vinculante.** Su modificación en la semana 2 requiere intervenir cuatro componentes de forma simultánea.

**La cola no es un almacén de consulta.** Es un mecanismo de tránsito. Las consultas sobre transacciones se resuelven contra los almacenes de la semana 2.

**El nombre de archivo proporcionado por el usuario constituye un vector de ataque conocido.** No debe utilizarse para construir la ruta de destino.

**El consumo de crédito determina la viabilidad de la semana 3.** Recursos en ejecución durante periodos de inactividad representan el principal riesgo de agotamiento.
