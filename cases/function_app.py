"""
Azure Function que consume la cola `casos-marcados` (Service Bus) y crea
el caso correspondiente en el almacén relacional. Capa delgada: la lógica
real vive en repository.py (testeable sin Azure, contra SQLite —
cases/tests/test_repository.py); `process_case_message` está separada del
binding decorado para poder probar la orquestación completa con un
repositorio real de SQLite y un mensaje simulado
(cases/tests/test_function_app.py), sin el runtime real de Azure Functions.

Entrega de Service Bus es at-least-once: `repository.create_case()` es
idempotente por `transaction_id` (ver cases/repository.py), así que un
mensaje entregado más de una vez no duplica el caso.
"""

import json
import logging

import azure.functions as func
from config import get_settings
from db import create_azure_sql_engine, create_session
from repository import CaseRepository, RuleActivationRecord, SqlAlchemyCaseRepository

app = func.FunctionApp()
logger = logging.getLogger(__name__)


@app.function_name(name="CaseCreationFunction")
@app.service_bus_queue_trigger(
    arg_name="msg", queue_name="casos-marcados", connection="ServiceBusConnection"
)
def case_creation_function(msg: func.ServiceBusMessage) -> None:
    body = json.loads(msg.get_body().decode("utf-8"))
    process_case_message(body)


def process_case_message(body: dict, repository: CaseRepository | None = None) -> None:
    owns_repository = repository is None
    if repository is None:
        settings = get_settings()
        engine = create_azure_sql_engine(settings.sql_server, settings.sql_database)
        repository = SqlAlchemyCaseRepository(create_session(engine))

    rule_activations = [
        RuleActivationRecord(rule_id=r["rule_id"], points=r["points"], details=r["details"])
        for r in body["rule_activations"]
    ]

    caso = repository.create_case(
        transaction_id=body["transaction_id"],
        account_id=body["account_id"],
        score=body["score"],
        rule_activations=rule_activations,
    )

    logger.info(
        "Caso %s creado (o ya existente) para transacción %s, score=%d",
        caso.id,
        body["transaction_id"],
        body["score"],
    )

    if owns_repository:
        repository.close()
