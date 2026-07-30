"""
Punto de entrada de la Azure Function de scoring — capa delgada, sin
lógica de negocio (esa vive en orchestration.py/rules.py, ambos testeables
sin Azure). Trigger de Event Grid: reacciona al evento "transaction.received"
publicado por la API tras persistir (api/app/services/ingestion.py), de
forma desacoplada — la API nunca espera a que esta función termine
(Azure-Semana2.md, restricción arquitectónica central de la semana).
"""

import logging

import azure.functions as func

from config import get_settings
from cosmos_repository import CosmosHistoryRepository
from orchestration import handle_transaction_event
from servicebus_publisher import ServiceBusCasePublisher

app = func.FunctionApp()
logger = logging.getLogger(__name__)


@app.function_name(name="ScoringFunction")
@app.event_grid_trigger(arg_name="event")
async def scoring_function(event: func.EventGridEvent) -> None:
    settings = get_settings()
    payload = event.get_json()

    history_repo = CosmosHistoryRepository(
        account_url=settings.cosmos_account_url,
        database_name=settings.cosmos_database_name,
        container_name=settings.cosmos_container_transactions,
    )
    case_publisher = ServiceBusCasePublisher(
        namespace_fqdn=settings.servicebus_namespace_fqdn,
        queue_name=settings.servicebus_queue_casos,
    )

    try:
        result = await handle_transaction_event(
            event_payload=payload,
            history_repo=history_repo,
            case_publisher=case_publisher,
            config=settings.to_scoring_config(),
            lookback_days=settings.history_lookback_days,
        )
        logger.info(
            "Transacción %s puntuada: score=%d reglas_activadas=%s",
            payload.get("transaction_id"),
            result.score,
            result.rule_ids,
        )
    finally:
        await history_repo.close()
        await case_publisher.close()