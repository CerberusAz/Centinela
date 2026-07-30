import logging
from datetime import datetime
from typing import Any

from app.models.transaction import TransactionIn
from app.storage.ports import TransactionStorage

logger = logging.getLogger(__name__)


class DualTransactionStorage:
    """
    Escribe la transacción cruda en dos stores con roles distintos
    (docs/decisiones-arquitectura.md, ADR sobre persistencia dual):

    - `primary` (Blob Storage en producción): autoridad de idempotencia y
      de `GET /transactions/{id}`. Bloqueante — si falla, falla la
      ingesta, igual que en semana 1.
    - `secondary` (Cosmos DB en producción): store operativo del motor de
      scoring (historial reciente por cuenta). Best-effort — un fallo se
      loguea y NO se relanza, para no romper la respuesta 201 ni la
      idempotencia que ya resolvió `primary`.

    Implementa el mismo `Protocol TransactionStorage` que sus dos
    componentes, así `IngestionService.ingest()` no cambia de firma
    (cumple la promesa de ADR-008 de semana 1: el endpoint y el servicio
    no se reescriben para cambiar de backend de persistencia).

    Consecuencia documentada del fallo best-effort: una transacción podría
    faltar en Cosmos si esa escritura falla. No hay reintento automático
    en esta semana — el motor de scoring simplemente no la verá en el
    historial hasta que exista otra escritura exitosa posterior.
    """

    def __init__(self, primary: TransactionStorage, secondary: TransactionStorage) -> None:
        self._primary = primary
        self._secondary = secondary

    async def exists(self, transaction_id: str) -> bool:
        return await self._primary.exists(transaction_id)

    async def get(self, transaction_id: str) -> dict[str, Any] | None:
        return await self._primary.get(transaction_id)

    async def save(self, transaction: TransactionIn, received_at: datetime) -> None:
        await self._primary.save(transaction, received_at)
        try:
            await self._secondary.save(transaction, received_at)
        except Exception:
            logger.exception(
                "Fallo al escribir la transacción %s en el store secundario "
                "(Cosmos DB); la escritura primaria ya se confirmó, la "
                "ingesta continúa.",
                transaction.transaction_id,
            )