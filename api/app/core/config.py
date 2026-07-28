from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageBackend(str, Enum):
    MEMORY = "memory"
    BLOB = "blob"


class EventPublisherBackend(str, Enum):
    NOOP = "noop"


class Settings(BaseSettings):
    """
    Configuración externalizada (sección 2.9). Todos los valores se leen de
    variables de entorno con prefijo CENTINELA_ (o de un archivo .env local
    para desarrollo). Incorporar un nuevo backend de storage o de mensajería
    en la semana 2 es un cambio de valor de configuración, no de código:
    ver app/storage/factory.py y app/messaging/publisher.py.
    """

    model_config = SettingsConfigDict(env_prefix="CENTINELA_", env_file=".env", extra="ignore")

    storage_backend: StorageBackend = StorageBackend.MEMORY
    blob_account_url: str | None = None
    blob_container_raw_transactions: str = "raw-transactions"

    event_publisher_backend: EventPublisherBackend = EventPublisherBackend.NOOP

    # Monto máximo aceptado, en unidad monetaria menor (ver docs/contrato-transaccion.md).
    # Valor por defecto conservador para un sistema de detección de fraude minorista;
    # ajustar por configuración según el perfil real de transacciones de Centinela.
    max_amount_minor_units: int = 10_000_000

    # Tolerancia de reloj para rechazar client_timestamp futuro (sección 2.9).
    clock_skew_tolerance_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
