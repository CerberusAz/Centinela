import logging
from typing import Any

from azure.eventgrid import EventGridEvent
from azure.eventgrid.aio import EventGridPublisherClient
from azure.identity.aio import DefaultAzureCredential

logger = logging.getLogger(__name__)


class EventGridEventPublisher:
    """
    Publica eventos en un topic personalizado de Event Grid
    (Azure-Semana2.md, sección 2.4: "distribución del evento de
    transacción"). Event Grid modela "notificar la ocurrencia de un
    evento" — reintentos con backoff y expiración (~24h), sin cola
    persistente consultable. La garantía de "no perder el caso" (sección
    2.4, cola de casos marcados) es responsabilidad de Service Bus en
    scoring/servicebus_publisher.py, un mecanismo deliberadamente distinto
    — ver docs/mensajeria-semana2.md.

    Autenticación exclusivamente AAD: rol de datos "EventGrid Data Sender"
    sobre el topic. NUNCA la clave de acceso del topic (`aeg-sas-key`) —
    mismo principio de cero claves del resto del proyecto.
    """

    def __init__(self, topic_endpoint: str) -> None:
        self._credential = DefaultAzureCredential()
        self._client = EventGridPublisherClient(topic_endpoint, self._credential)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = EventGridEvent(
            event_type=event_type,
            data=payload,
            subject=f"centinela/{event_type}",
            data_version="1.0",
        )
        await self._client.send(event)

    async def close(self) -> None:
        await self._client.close()
        await self._credential.close()