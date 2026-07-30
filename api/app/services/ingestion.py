from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.messaging.publisher import EventPublisher, get_event_publisher
from app.models.transaction import TransactionIn
from app.storage.factory import get_transaction_storage
from app.storage.ports import TransactionStorage


class ContractValidationError(Exception):
    """
    Violación semántica del contrato que no puede expresarse como una
    restricción de forma en el modelo Pydantic (depende de configuración o
    del reloj del servidor). Se homologa a HTTP 400, igual que los errores
    de forma (ver app/main.py).
    """

    def __init__(self, message: str) -> None:
        self.message = message


@dataclass
class IngestionResult:
    status_code: int
    body: dict[str, Any]


class IngestionService:
    """
    Orquesta la secuencia recibir -> validar -> persistir -> responder
    (sección 2.9). La API (app/api/routes.py) no contiene esta lógica: solo
    delega aquí. El motor de scoring de la semana 2 NO vive en esta clase.
    """

    def __init__(
        self,
        storage: TransactionStorage,
        publisher: EventPublisher,
        settings: Settings,
    ) -> None:
        self._storage = storage
        self._publisher = publisher
        self._settings = settings

    async def ingest(self, transaction: TransactionIn) -> IngestionResult:
        self._validate_semantics(transaction)

        if await self._storage.exists(transaction.transaction_id):
            # Estrategia de idempotencia (docs/idempotencia.md): una transacción
            # ya persistida no se vuelve a procesar ni a publicar como evento.
            return IngestionResult(
                status_code=200,
                body={
                    "transaction_id": transaction.transaction_id,
                    "status": "already_accepted",
                },
            )

        server_received_at = datetime.now(timezone.utc)
        await self._storage.save(transaction, server_received_at)

        # --- Punto de inserción semana 2 -----------------------------------
        # Tras persistir y antes de responder es donde se publica el evento
        # "transaction.received" para el motor de scoring asíncrono. El
        # publisher real reemplaza a NoOpEventPublisher por configuración
        # (CENTINELA_EVENT_PUBLISHER_BACKEND); esta línea no cambia.
        #
        # El payload lleva la transacción completa, no solo el id: con
        # consistencia Session en Cosmos DB, la API y el motor de scoring
        # son procesos con clientes distintos, sin garantía automática de
        # que la Function vea el registro que la API acaba de escribir. Al
        # viajar la transacción completa en el evento, el motor nunca
        # depende de releer Cosmos para SU PROPIA transacción — solo
        # consulta Cosmos para el historial de transacciones ANTERIORES de
        # la cuenta, donde una leve staleness sí es aceptable (ver
        # docs/decisiones-arquitectura.md).
        await self._publisher.publish(
            event_type="transaction.received",
            payload={
                "transaction_id": transaction.transaction_id,
                "account_id": transaction.account_id,
                "amount_minor_units": transaction.amount_minor_units,
                "currency": transaction.currency,
                "server_received_at": server_received_at.isoformat(),
                "location": transaction.location.model_dump(),
                "merchant": transaction.merchant.model_dump(),
            },
        )
        # ---------------------------------------------------------------------

        return IngestionResult(
            status_code=201,
            body={
                "transaction_id": transaction.transaction_id,
                "status": "accepted",
                "received_at": server_received_at.isoformat(),
            },
        )

    async def get(self, transaction_id: str) -> dict[str, Any] | None:
        return await self._storage.get(transaction_id)

    def _validate_semantics(self, transaction: TransactionIn) -> None:
        now = datetime.now(timezone.utc)
        tolerance = self._settings.clock_skew_tolerance_seconds
        if (transaction.client_timestamp - now).total_seconds() > tolerance:
            raise ContractValidationError("client_timestamp no puede estar en el futuro")

        if transaction.amount_minor_units > self._settings.max_amount_minor_units:
            raise ContractValidationError(
                "amount_minor_units excede el máximo permitido "
                f"({self._settings.max_amount_minor_units})"
            )


def get_ingestion_service(
    storage: TransactionStorage = Depends(get_transaction_storage),
    publisher: EventPublisher = Depends(get_event_publisher),
    settings: Settings = Depends(get_settings),
) -> IngestionService:
    return IngestionService(storage=storage, publisher=publisher, settings=settings)
