from db import create_session, create_sqlite_engine
from function_app import process_case_message
from models import ESTADO_ABIERTO
from repository import SqlAlchemyCaseRepository


def _service_bus_message_body(**overrides):
    body = {
        "transaction_id": "tx-1",
        "account_id": "acc-1",
        "score": 80,
        "rule_activations": [
            {"rule_id": "velocidad", "points": 30, "details": {"transaction_count": 5}},
            {"rule_id": "geo_imposible", "points": 50, "details": {"implied_speed_kmh": 14000}},
        ],
    }
    body.update(overrides)
    return body


def _repository():
    engine = create_sqlite_engine()
    return SqlAlchemyCaseRepository(create_session(engine))


def test_process_case_message_creates_case_with_rule_detail():
    repository = _repository()

    process_case_message(_service_bus_message_body(), repository=repository)

    caso = repository.get_case_by_transaction("tx-1")
    assert caso is not None
    assert caso.account_id == "acc-1"
    assert caso.score == 80
    assert caso.estado_codigo == ESTADO_ABIERTO
    assert "velocidad" in caso.reglas_activadas_json
    assert "geo_imposible" in caso.reglas_activadas_json


def test_process_case_message_records_creation_audit():
    repository = _repository()

    process_case_message(_service_bus_message_body(), repository=repository)

    caso = repository.get_case_by_transaction("tx-1")
    assert len(caso.auditoria) == 1
    assert caso.auditoria[0].valor_nuevo == ESTADO_ABIERTO


def test_process_case_message_is_idempotent_for_redelivered_message():
    """
    Simula la garantía at-least-once de Service Bus: el mismo mensaje
    (mismo transaction_id) llega dos veces -- no debe crear un segundo
    caso (Azure-Semana2.md, entregable 10: "al restablecerse el
    consumidor, todos los casos marcados ... se procesan sin pérdidas",
    lo cual solo es seguro si el reprocesamiento es idempotente).
    """
    repository = _repository()
    body = _service_bus_message_body()

    process_case_message(body, repository=repository)
    process_case_message(body, repository=repository)  # entrega duplicada

    caso = repository.get_case_by_transaction("tx-1")
    assert caso is not None
    # Solo una creación registrada en auditoría -> no hubo un segundo caso.
    assert len(caso.auditoria) == 1


def test_process_case_message_handles_case_with_no_activated_rules():
    repository = _repository()

    process_case_message(_service_bus_message_body(score=0, rule_activations=[]), repository=repository)

    caso = repository.get_case_by_transaction("tx-1")
    assert caso.score == 0
    assert caso.reglas_activadas_json == "[]"
