import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models.transaction import TransactionIn
from app.storage.dual_storage import DualTransactionStorage
from app.storage.memory_storage import InMemoryTransactionStorage


def _run(coro):
    return asyncio.run(coro)


class FailingSecondaryStorage:
    """Doble de prueba: simula un backend secundario (Cosmos) que siempre falla al escribir."""

    def __init__(self) -> None:
        self.save_attempts = 0

    async def exists(self, transaction_id: str) -> bool:
        raise AssertionError("DualTransactionStorage no debe consultar exists() en el secundario")

    async def get(self, transaction_id: str) -> dict[str, Any] | None:
        raise AssertionError("DualTransactionStorage no debe consultar get() en el secundario")

    async def save(self, transaction: TransactionIn, received_at: datetime) -> None:
        self.save_attempts += 1
        raise RuntimeError("Cosmos no disponible (simulado)")


def _transaction(**overrides) -> TransactionIn:
    payload = {
        "transaction_id": str(uuid.uuid4()),
        "account_id": "acc-001",
        "amount_minor_units": 1500,
        "currency": "USD",
        "client_timestamp": datetime.now(timezone.utc).isoformat(),
        "location": {"latitude": 4.6097, "longitude": -74.0817},
        "merchant": {"merchant_id": "merch-001", "category": "grocery"},
    }
    payload.update(overrides)
    return TransactionIn(**payload)


def test_save_writes_to_both_stores_on_success():
    async def scenario():
        primary = InMemoryTransactionStorage()
        secondary = InMemoryTransactionStorage()
        dual = DualTransactionStorage(primary=primary, secondary=secondary)
        transaction = _transaction()

        await dual.save(transaction, datetime.now(timezone.utc))

        assert await primary.exists(transaction.transaction_id) is True
        assert await secondary.exists(transaction.transaction_id) is True

    _run(scenario())


def test_save_survives_secondary_failure_without_raising():
    async def scenario():
        primary = InMemoryTransactionStorage()
        secondary = FailingSecondaryStorage()
        dual = DualTransactionStorage(primary=primary, secondary=secondary)
        transaction = _transaction()

        # No debe relanzar la excepción del store secundario.
        await dual.save(transaction, datetime.now(timezone.utc))

        assert secondary.save_attempts == 1
        assert await primary.exists(transaction.transaction_id) is True

    _run(scenario())


def test_exists_and_get_delegate_only_to_primary():
    async def scenario():
        primary = InMemoryTransactionStorage()
        secondary = FailingSecondaryStorage()  # nunca debe tocarse para exists()/get()
        dual = DualTransactionStorage(primary=primary, secondary=secondary)
        transaction = _transaction()
        await primary.save(transaction, datetime.now(timezone.utc))

        assert await dual.exists(transaction.transaction_id) is True
        document = await dual.get(transaction.transaction_id)
        assert document is not None

    _run(scenario())


def test_exists_false_when_primary_has_nothing():
    async def scenario():
        dual = DualTransactionStorage(
            primary=InMemoryTransactionStorage(), secondary=InMemoryTransactionStorage()
        )
        assert await dual.exists(str(uuid.uuid4())) is False

    _run(scenario())