"""
Orquesta la secuencia del motor de scoring (Azure-Semana2.md, sección 2.3,
pasos 1-6), separada de `function_app.py` (el binding real de Azure
Functions) para poder probarla con dobles de `HistoryRepository`/
`CasePublisher` en memoria, sin tocar Cosmos DB ni Service Bus reales
(scoring/tests/test_orchestration.py).
"""

from datetime import datetime, timedelta
from typing import Any, Protocol

from rules import ScoringConfig, ScoringResult, evaluate_all


class HistoryRepository(Protocol):
    async def query_recent_history(
        self, account_id: str, exclude_transaction_id: str, since: datetime
    ) -> list[dict[str, Any]]: ...

    async def persist_score(self, transaction_id: str, account_id: str, result: ScoringResult) -> None: ...


class CasePublisher(Protocol):
    async def publish_case(self, transaction_id: str, account_id: str, result: ScoringResult) -> None: ...


def _transaction_from_event(payload: dict[str, Any]) -> dict[str, Any]:
    """
    El payload del evento (publicado por api/app/services/ingestion.py)
    trae la transacción completa, no solo el id — ver el comentario en
    ese archivo sobre por qué (consistencia Session de Cosmos DB entre
    procesos distintos).
    """
    return {
        "transaction_id": payload["transaction_id"],
        "account_id": payload["account_id"],
        "amount_minor_units": payload["amount_minor_units"],
        "server_received_at": datetime.fromisoformat(payload["server_received_at"]),
        "location": payload["location"],
        "merchant": payload["merchant"],
    }


async def handle_transaction_event(
    event_payload: dict[str, Any],
    history_repo: HistoryRepository,
    case_publisher: CasePublisher,
    config: ScoringConfig,
    lookback_days: int = 30,
) -> ScoringResult:
    """
    1. Recibir el evento — ya deserializado por quien llama (`event_payload`).
    2. Consultar el historial reciente de la cuenta.
    3-4. Evaluar las 4 reglas y sumar puntos (rules.evaluate_all).
    5. Persistir el score junto a la transacción.
    6. Si supera el umbral, publicar apertura de caso.
    """
    transaction = _transaction_from_event(event_payload)
    account_id = transaction["account_id"]
    transaction_id = transaction["transaction_id"]

    since = transaction["server_received_at"] - timedelta(days=lookback_days)
    history = await history_repo.query_recent_history(
        account_id=account_id, exclude_transaction_id=transaction_id, since=since
    )

    result = evaluate_all(transaction, history, config)

    await history_repo.persist_score(transaction_id=transaction_id, account_id=account_id, result=result)

    if result.exceeds_threshold(config):
        await case_publisher.publish_case(transaction_id=transaction_id, account_id=account_id, result=result)

    return result