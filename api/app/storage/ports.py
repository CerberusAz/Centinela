from datetime import datetime
from typing import Any, Protocol

from app.models.transaction import TransactionIn


class TransactionStorage(Protocol):
    """
    Puerto de persistencia de la transacción cruda (sección 2.9, paso 3).
    Cualquier implementación (memoria, Blob Storage, y en el futuro un
    almacén relacional/documental de la semana 2) debe cumplir esta interfaz
    para que la capa de servicio no cambie.
    """

    async def exists(self, transaction_id: str) -> bool: ...

    async def save(self, transaction: TransactionIn, received_at: datetime) -> None: ...

    async def get(self, transaction_id: str) -> dict[str, Any] | None: ...
