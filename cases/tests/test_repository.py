import pytest
from db import create_session, create_sqlite_engine
from models import ESTADO_ABIERTO, ESTADO_ASIGNADO, ESTADO_RESUELTO
from repository import CaseNotFoundError, RuleActivationRecord, SqlAlchemyCaseRepository
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def repo():
    engine = create_sqlite_engine()
    session = create_session(engine)
    yield SqlAlchemyCaseRepository(session)
    session.close()


def _rule_activations():
    return [
        RuleActivationRecord(rule_id="velocidad", points=30, details={"transaction_count": 5}),
        RuleActivationRecord(rule_id="geo_imposible", points=50, details={"implied_speed_kmh": 14000}),
    ]


def test_create_case_persists_score_and_rule_detail(repo):
    caso = repo.create_case(
        transaction_id="tx-1", account_id="acc-1", score=80, rule_activations=_rule_activations()
    )

    assert caso.id is not None
    assert caso.transaction_id == "tx-1"
    assert caso.estado_codigo == ESTADO_ABIERTO
    assert "velocidad" in caso.reglas_activadas_json
    assert "geo_imposible" in caso.reglas_activadas_json


def test_create_case_records_audit_entry(repo):
    caso = repo.create_case(
        transaction_id="tx-1", account_id="acc-1", score=80, rule_activations=_rule_activations()
    )

    assert len(caso.auditoria) == 1
    assert caso.auditoria[0].campo_modificado == "estado_codigo"
    assert caso.auditoria[0].valor_anterior is None
    assert caso.auditoria[0].valor_nuevo == ESTADO_ABIERTO


def test_create_case_is_idempotent_for_same_transaction(repo):
    first = repo.create_case(
        transaction_id="tx-1", account_id="acc-1", score=80, rule_activations=_rule_activations()
    )
    second = repo.create_case(
        transaction_id="tx-1", account_id="acc-1", score=999, rule_activations=[]
    )

    # Misma transacción entregada dos veces (at-least-once de Service Bus)
    # -> mismo caso, no un duplicado; el segundo intento no pisa el score.
    assert first.id == second.id
    assert second.score == 80


def test_assign_case_updates_state_and_records_two_audit_entries(repo):
    caso = repo.create_case(
        transaction_id="tx-1", account_id="acc-1", score=80, rule_activations=_rule_activations()
    )

    asignacion = repo.assign_case(caso.id, analista="ana@centinela.test", assigned_by="supervisor@centinela.test")

    refreshed = repo.get_case(caso.id)
    assert refreshed.estado_codigo == ESTADO_ASIGNADO
    assert asignacion.analista == "ana@centinela.test"
    assert len(refreshed.asignaciones) == 1
    # 1 de creación + 2 de asignación (cambio de estado + analista asignado)
    assert len(refreshed.auditoria) == 3


def test_assign_case_raises_for_unknown_case(repo):
    with pytest.raises(CaseNotFoundError):
        repo.assign_case("no-existe", analista="ana@centinela.test", assigned_by="supervisor@centinela.test")


def test_resolve_case_updates_state_and_records_decision(repo):
    caso = repo.create_case(
        transaction_id="tx-1", account_id="acc-1", score=80, rule_activations=_rule_activations()
    )
    repo.assign_case(caso.id, analista="ana@centinela.test", assigned_by="supervisor@centinela.test")

    resolucion = repo.resolve_case(
        caso.id,
        decision="fraude_confirmado",
        analista="ana@centinela.test",
        observaciones="Confirmado con el titular.",
        resolved_by="ana@centinela.test",
    )

    refreshed = repo.get_case(caso.id)
    assert refreshed.estado_codigo == ESTADO_RESUELTO
    assert refreshed.resolucion.decision == "fraude_confirmado"
    assert resolucion.observaciones == "Confirmado con el titular."


def test_resolve_case_raises_for_unknown_case(repo):
    with pytest.raises(CaseNotFoundError):
        repo.resolve_case(
            "no-existe",
            decision="fraude_confirmado",
            analista="ana@centinela.test",
            observaciones=None,
            resolved_by="ana@centinela.test",
        )


def test_resolve_case_twice_violates_unique_constraint(repo):
    caso = repo.create_case(
        transaction_id="tx-1", account_id="acc-1", score=80, rule_activations=_rule_activations()
    )
    repo.resolve_case(
        caso.id, decision="fraude_confirmado", analista="ana", observaciones=None, resolved_by="ana"
    )

    with pytest.raises(IntegrityError):
        repo.resolve_case(
            caso.id, decision="falso_positivo", analista="ana", observaciones=None, resolved_by="ana"
        )


def test_get_case_by_transaction_returns_none_when_absent(repo):
    assert repo.get_case_by_transaction("no-existe") is None