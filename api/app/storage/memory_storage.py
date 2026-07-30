from datetime import datetime
from typing import Any

from app.models.transaction import TransactionIn


class InMemoryTransactionStorage:
    """
    Implementación para desarrollo local y pruebas. No usar en Azure:
    los datos no sobreviven un reinicio del proceso.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    async def exists(self, transaction_id: str) -> bool:
        return transaction_id in self._store

    async def save(self, transaction: TransactionIn, received_at: datetime) -> None:
        self._store.setdefault(
            transaction.transaction_id,
            {
                "transaction": transaction.model_dump(mode="json"),
                "server_received_at": received_at.isoformat(),
            },
        )

    async def get(self, transaction_id: str) -> dict[str, Any] | None:
        return self._store.get(transaction_id)
