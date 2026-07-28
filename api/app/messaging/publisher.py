from typing import Any, Protocol

from fastapi import Depends

from app.core.config import EventPublisherBackend, Settings, get_settings


class EventPublisher(Protocol):
    async def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...


class NoOpEventPublisher:
    """
    Implementación de la semana 1: la mensajería de eventos está fuera de
    alcance (Azure-Semana1.md, sección 1). Existe para que el punto de
    inserción en IngestionService.ingest() ya esté cableado en capas; en la
    semana 2 se sustituye por un publisher real (p. ej. Service Bus) cambiando
    CENTINELA_EVENT_PUBLISHER_BACKEND por configuración, sin reescribir el
    endpoint ni el servicio de ingesta.
    """

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        return None


_publisher_instance: EventPublisher | None = None


def get_event_publisher(settings: Settings = Depends(get_settings)) -> EventPublisher:
    global _publisher_instance
    if _publisher_instance is None:
        if settings.event_publisher_backend == EventPublisherBackend.NOOP:
            _publisher_instance = NoOpEventPublisher()
        else:
            raise RuntimeError(f"Publisher no soportado: {settings.event_publisher_backend}")
    return _publisher_instance
