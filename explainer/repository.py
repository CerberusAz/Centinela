"""
Repositorio de casos para el explicador.

Separa el acceso a SQL (Azure SQL en producción, SQLite en tests) de
la lógica de generación de explicaciones. El explicador necesita:
  1. Leer casos sin explicación (explicacion_texto IS NULL).
  2. Escribir la explicación generada sobre el caso.

`Caso` se importa del módulo de models de la Function de casos (cases/models.py),
que es el esquema canónico del almacén relacional del proyecto. En el
contenedor del explicador, ese módulo se copia al directorio de trabajo.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from models import Caso


class ExplainerRepository(Protocol):
    """
    Interfaz mínima del repositorio: lo único que el explicador
    necesita leer y escribir, inyectable en tests sin Azure SQL.
    """

    def get_cases_pending_explanation(self, limit: int = 50) -> list[Caso]: ...

    def save_explanation(self, case_id: str, explanation_text: str) -> None: ...

    def get_case(self, case_id: str) -> Caso | None: ...

    def close(self) -> None: ...


class SqlAlchemyExplainerRepository:
    """
    Implementación contra SQLAlchemy (Azure SQL en producción,
    SQLite en tests). La columna `explicacion_texto` se añade al
    esquema de la tabla `caso` en explainer/schema_patch.sql.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_cases_pending_explanation(self, limit: int = 50) -> list[Caso]:
        """
        Devuelve los casos con `explicacion_texto` NULL: son los que se
        abrieron mientras el explicador estaba inactivo, o recién creados.
        Al restablecerse el componente, este método los recupera todos y
        garantiza que ninguno quede sin explicación indefinidamente.
        """
        stmt = (
            select(Caso)
            .where(text("explicacion_texto IS NULL"))
            .limit(limit)
            .order_by(Caso.fecha_apertura)
        )
        return list(self._session.execute(stmt).scalars().all())

    def save_explanation(self, case_id: str, explanation_text: str) -> None:
        caso = self._session.get(Caso, case_id)
        if caso is None:
            raise ValueError(f"Caso '{case_id}' no encontrado al guardar explicación")
        caso.explicacion_texto = explanation_text  # type: ignore[attr-defined]
        self._session.commit()

    def get_case(self, case_id: str) -> Caso | None:
        return self._session.get(Caso, case_id)

    def close(self) -> None:
        self._session.close()
