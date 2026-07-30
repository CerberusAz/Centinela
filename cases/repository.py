"""
Capa de repositorio del almacén de casos. Separada de `db.py` (conexión
real) a propósito: `SqlAlchemyCaseRepository` recibe una `Session` ya
construida, así se puede probar de punta a punta contra SQLite en memoria
(cases/tests/test_repository.py) sin ninguna dependencia de Azure, y el
mismo código sirve sin cambios contra Azure SQL en producción.
"""

import json
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import ESTADO_ABIERTO, ESTADO_ASIGNADO, ESTADO_RESUELTO, Asignacion, Auditoria, Caso, Resolucion


class CaseNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class RuleActivationRecord:
    rule_id: str
    points: int
    details: dict


class CaseRepository(Protocol):
    def create_case(
        self,
        transaction_id: str,
        account_id: str,
        score: int,
        rule_activations: list[RuleActivationRecord],
        opened_by: str = "motor-scoring",
    ) -> Caso: ...

    def assign_case(self, case_id: str, analista: str, assigned_by: str) -> Asignacion: ...

    def resolve_case(
        self,
        case_id: str,
        decision: str,
        analista: str,
        observaciones: str | None,
        resolved_by: str,
    ) -> Resolucion: ...

    def get_case(self, case_id: str) -> Caso | None: ...

    def get_case_by_transaction(self, transaction_id: str) -> Caso | None: ...

    def close(self) -> None: ...


class SqlAlchemyCaseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_case(
        self,
        transaction_id: str,
        account_id: str,
        score: int,
        rule_activations: list[RuleActivationRecord],
        opened_by: str = "motor-scoring",
    ) -> Caso:
        existing = self.get_case_by_transaction(transaction_id)
        if existing is not None:
            # Idempotencia: la cola de casos garantiza entrega "al menos
            # una vez" (docs/mensajeria-semana2.md); una segunda entrega
            # del mismo mensaje no debe crear un segundo caso.
            return existing

        caso = Caso(
            transaction_id=transaction_id,
            account_id=account_id,
            score=score,
            reglas_activadas_json=json.dumps(
                [
                    {"rule_id": a.rule_id, "points": a.points, "details": a.details}
                    for a in rule_activations
                ]
            ),
            estado_codigo=ESTADO_ABIERTO,
        )
        self._session.add(caso)
        self._session.flush()  # asigna caso.id antes de auditar

        self._record_audit(caso.id, "estado_codigo", None, ESTADO_ABIERTO, opened_by)
        self._session.commit()
        return caso

    def assign_case(self, case_id: str, analista: str, assigned_by: str) -> Asignacion:
        caso = self._require_case(case_id)

        asignacion = Asignacion(caso_id=case_id, analista=analista)
        self._session.add(asignacion)

        valor_anterior = caso.estado_codigo
        caso.estado_codigo = ESTADO_ASIGNADO
        self._record_audit(case_id, "estado_codigo", valor_anterior, ESTADO_ASIGNADO, assigned_by)
        self._record_audit(case_id, "analista_asignado", None, analista, assigned_by)

        self._session.commit()
        return asignacion

    def resolve_case(
        self,
        case_id: str,
        decision: str,
        analista: str,
        observaciones: str | None,
        resolved_by: str,
    ) -> Resolucion:
        caso = self._require_case(case_id)

        resolucion = Resolucion(
            caso_id=case_id, decision=decision, analista=analista, observaciones=observaciones
        )
        self._session.add(resolucion)

        valor_anterior = caso.estado_codigo
        caso.estado_codigo = ESTADO_RESUELTO
        self._record_audit(case_id, "estado_codigo", valor_anterior, ESTADO_RESUELTO, resolved_by)
        self._record_audit(case_id, "decision", None, decision, resolved_by)

        self._session.commit()
        return resolucion

    def get_case(self, case_id: str) -> Caso | None:
        return self._session.get(Caso, case_id)

    def get_case_by_transaction(self, transaction_id: str) -> Caso | None:
        stmt = select(Caso).where(Caso.transaction_id == transaction_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def close(self) -> None:
        self._session.close()

    def _require_case(self, case_id: str) -> Caso:
        caso = self.get_case(case_id)
        if caso is None:
            raise CaseNotFoundError(f"No existe un caso con id '{case_id}'")
        return caso

    def _record_audit(
        self, caso_id: str, campo: str, valor_anterior: str | None, valor_nuevo: str, modificado_por: str
    ) -> None:
        """
        Único punto de escritura sobre Auditoria — se invoca desde todos
        los métodos que cambian estado, nunca es opcional. No existe un
        método público para modificar Auditoria directamente.
        """
        self._session.add(
            Auditoria(
                caso_id=caso_id,
                campo_modificado=campo,
                valor_anterior=valor_anterior,
                valor_nuevo=valor_nuevo,
                modificado_por=modificado_por,
            )
        )
