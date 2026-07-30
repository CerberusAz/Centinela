from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageBackend(str, Enum):
    MEMORY = "memory"
    BLOB = "blob"
    # Semana 2: escribe a Blob (autoridad de idempotencia/lookup) y además a
    # Cosmos DB (store operativo del motor de scoring). Ver
    # app/storage/dual_storage.py.
    DUAL = "dual"


class EventPublisherBackend(str, Enum):
    NOOP = "noop"
    # Semana 2: distribución del evento de transacción (Azure-Semana2.md
    # 2.4). Ver app/messaging/event_grid_publisher.py.
    EVENT_GRID = "eventgrid"


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
    blob_container_raw_transactions: str = "transacciones"

    # Contenedor de documentos de verificación de identidad (sección 2.10).
    # El nombre del blob lo genera el sistema, nunca el usuario.
    identity_blob_container: str = "identity-documents"

    # Tamaño máximo de archivo para carga de documentos de identidad (sección 2.10).
    # Default: 10 MB. Ajustar por configuración según el perfil de documentos esperados.
    max_document_size_bytes: int = 10_485_760  # 10 MB

    event_publisher_backend: EventPublisherBackend = EventPublisherBackend.NOOP

    # Semana 2 — store operativo de Cosmos DB (obligatorio si
    # storage_backend=dual). Ver docs/justificacion-particionamiento-cosmos.md.
    cosmos_account_url: str | None = None
    cosmos_database_name: str = "centinela"
    cosmos_container_transactions: str = "transactions"

    # Semana 2 — topic de Event Grid (obligatorio si
    # event_publisher_backend=eventgrid).
    event_grid_topic_endpoint: str | None = None

    # Monto máximo aceptado, en unidad monetaria menor (ver docs/contrato-transaccion.md).
    # Valor por defecto conservador para un sistema de detección de fraude minorista;
    # ajustar por configuración según el perfil real de transacciones de Centinela.
    max_amount_minor_units: int = 10_000_000

    # Tolerancia de reloj para rechazar client_timestamp futuro (sección 2.9).
    clock_skew_tolerance_seconds: int = 60

    # Limitación de tasa de POST /transactions (Azure-Semana2.md, sección
    # 2.7). Justificación de los valores por defecto en
    # docs/limite-tasa-api.md. Ventana deslizante por IP de origen.
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
