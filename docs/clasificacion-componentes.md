# Tabla de clasificación de componentes

Entregable 7. Identifica cada componente previsto del sistema Centinela a
partir del recorrido de una transacción (Azure-Semana1.md, sección 2.5),
su modelo de servicio de nube y la distribución de responsabilidades entre
la célula y el proveedor (Azure), según el modelo de responsabilidad
compartida.

**Modelo de servicio:** IaaS (infraestructura como servicio — la célula
administra SO y runtime), PaaS (plataforma como servicio — Azure administra
SO/runtime, la célula administra código, configuración y datos), SaaS/AI
(servicio totalmente gestionado consumido vía API — la célula solo
administra los datos que envía y el acceso).

| # | Componente | Aparece en | Modelo | Responsabilidad de la célula | Responsabilidad del proveedor (Azure) |
|---|---|---|---|---|---|
| 1 | Cliente / canal de origen (app, POS, e-commerce) | Semana 1 | Fuera del sistema | Autenticarse ante la API con la credencial que le corresponda; construir el payload conforme al contrato | Ninguna — no es un recurso de Azure |
| 2 | Azure App Service (API de ingesta) | Semana 1 | PaaS | Código de la API, validación del contrato, configuración de la app, integración con VNet, gestión de la Managed Identity asignada | Runtime, parcheo de SO/lenguaje, disponibilidad de la plataforma, escalado del plan de servicio |
| 3 | Virtual Network, subredes, NSG | Semana 1 | Infraestructura de red gestionada | Diseño de topología, rangos de direcciones, reglas de tráfico (denegar por defecto), asignación de subredes a componentes | Enrutamiento físico, aislamiento entre tenants, disponibilidad del fabric de red |
| 4 | Microsoft Entra ID / Managed Identity | Semana 1 | SaaS (identidad) | Definición de roles y permisos (matriz de la sección 2.6), asignación de identidades gestionadas a los recursos, revisión de permisos de menor privilegio | Emisión y validación de tokens, disponibilidad del directorio, protocolo de autenticación |
| 5 | Blob Storage — contenedor `raw-transactions` (transacción cruda) | Semana 1 | PaaS | Convención de nombres de blob, formato del documento persistido, control de acceso (solo Managed Identity de la API), ciclo de vida | Durabilidad, redundancia configurada, disponibilidad del servicio, cifrado en reposo |
| 6 | Blob Storage — contenedor de documentos de verificación de identidad | Semana 1 (sección 2.10) | PaaS | Política de acceso delegado (SAS/identidad), nivel de redundancia, política de ciclo de vida, validación de tipo de archivo por contenido, límite de tamaño | Durabilidad, disponibilidad, cifrado en reposo |
| 7 | Cola de ingesta (Storage Queue / Service Bus) | Semana 1 (sección 2.11) | PaaS | Política de mensajes fallidos (dead-lettering), diseño de consumidores, control de acceso | Durabilidad de los mensajes en tránsito, disponibilidad del servicio, garantías de entrega de la plataforma |
| 8 | Motor de scoring (previsto) | Semana 2 | PaaS / serverless (Functions) | Lógica de las reglas de detección, consumo de eventos de la cola, escritura en los almacenes | Runtime de ejecución, escalado automático, disponibilidad de la plataforma |
| 9 | Base de datos relacional (previsto) | Semana 2 | PaaS (DBaaS) | Esquema, índices, control de acceso a nivel de datos, backups aplicados a la política de retención | Parcheo del motor, alta disponibilidad, backups de infraestructura, cifrado en reposo |
| 10 | Base de datos documental (previsto) | Semana 2 | PaaS (DBaaS) | Modelo de documentos, particionamiento, control de acceso | Igual que #9 |
| 11 | Servicio de reconocimiento documental (previsto, p. ej. Azure AI Document Intelligence) | Semana 2/3 | SaaS (IA gestionada) | Documentos que se envían al servicio, interpretación de resultados, control de acceso a la API del servicio | Modelo de IA, entrenamiento, disponibilidad, cumplimiento del nivel de servicio publicado |
| 12 | Escalado del App Service Plan (previsto) | Semana 3 | PaaS | Definición de reglas de auto-escalado, presupuesto asociado | Ejecución del escalado, aislamiento entre instancias |

**Nota sobre el límite IaaS/PaaS/SaaS en este proyecto:** Centinela no
contempla ningún componente IaaS (no se aprovisionan máquinas virtuales) —
decisión coherente con la sección 2.9, que exige desplegar en "el nivel de
servicio más bajo que soporte la integración con la red virtual" dentro de
un modelo PaaS, y con el control de costo de la sección 2.1 (una VM propia
implica gestionar parcheo y disponibilidad, un costo operativo que la
suscripción gratuita de 30 días no puede absorber).
