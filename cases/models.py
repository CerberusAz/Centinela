"""
Modelo relacional del almacén de casos (Azure-Semana2.md, sección 2.2).

Cinco entidades mínimas exigidas: Caso, Estado, Asignación, Resolución,
Auditoría. Declarado con SQLAlchemy para poder ejecutarlo tanto contra
SQLite en memoria (tests/desarrollo local, sin Azure) como contra Azure SQL
en producción (ver cases/db.py) sin duplicar el esquema — `cases/schema.sql`
es el DDL T-SQL equivalente para ejecución manual contra Azure SQL real.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# Códigos de estado del catálogo (Estado.codigo). No son un enum de Python
# a propósito: la tabla Estado es el catálogo real, editable por el equipo
# de operaciones sin tocar código — estas constantes son solo los valores
# que el propio pipeline necesita nombrar por código.
ESTADO_ABIERTO = "abierto"
ESTADO_ASIGNADO = "asignado"
ESTADO_RESUELTO = "resuelto"

ESTADOS_INICIALES = (
    (ESTADO_ABIERTO, "Caso recién creado, sin analista asignado"),
    (ESTADO_ASIGNADO, "Caso asignado a un analista, en análisis"),
    (ESTADO_RESUELTO, "Caso con decisión final registrada"),
)


class Estado(Base):
    """Catálogo de estados posibles de un caso."""

    __tablename__ = "estado"

    codigo: Mapped[str] = mapped_column(String(32), primary_key=True)
    descripcion: Mapped[str] = mapped_column(String(256))


class Caso(Base):
    """
    Un caso de fraude abierto por el motor de scoring cuando una
    transacción supera el umbral configurado.

    `transaction_id` es único: un caso por transacción. Esto también da
    idempotencia a la creación del caso — si el consumidor de la cola de
    casos recibe el mismo mensaje más de una vez (entrega at-least-once),
    la segunda inserción se detecta por esta restricción en vez de crear
    un caso duplicado.
    """

    __tablename__ = "caso"
    __table_args__ = (UniqueConstraint("transaction_id", name="uq_caso_transaction_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    transaction_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    reglas_activadas_json: Mapped[str] = mapped_column(Text, nullable=False)
    estado_codigo: Mapped[str] = mapped_column(
        String(32), ForeignKey("estado.codigo"), nullable=False, default=ESTADO_ABIERTO
    )
    fecha_apertura: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    estado: Mapped["Estado"] = relationship()
    asignaciones: Mapped[list["Asignacion"]] = relationship(
        back_populates="caso", order_by="Asignacion.fecha_asignacion"
    )
    resolucion: Mapped["Resolucion | None"] = relationship(back_populates="caso", uselist=False)
    auditoria: Mapped[list["Auditoria"]] = relationship(back_populates="caso", order_by="Auditoria.fecha")


class Asignacion(Base):
    """Relación caso-analista. Un caso puede tener varias a lo largo del tiempo (reasignaciones)."""

    __tablename__ = "asignacion"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    caso_id: Mapped[str] = mapped_column(String(36), ForeignKey("caso.id"), nullable=False, index=True)
    analista: Mapped[str] = mapped_column(String(128), nullable=False)
    fecha_asignacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    caso: Mapped["Caso"] = relationship(back_populates="asignaciones")


class Resolucion(Base):
    """Decisión final sobre un caso. Una sola resolución por caso (la decisión que cierra el caso)."""

    __tablename__ = "resolucion"
    __table_args__ = (UniqueConstraint("caso_id", name="uq_resolucion_caso_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    caso_id: Mapped[str] = mapped_column(String(36), ForeignKey("caso.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)  # p. ej. fraude_confirmado, falso_positivo
    analista: Mapped[str] = mapped_column(String(128), nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    observaciones: Mapped[str] = mapped_column(Text, nullable=True)

    caso: Mapped["Caso"] = relationship(back_populates="resolucion")


class Auditoria(Base):
    """
    Registro inmutable de cada cambio de estado de un caso: qué cambió,
    quién y cuándo (sección 2.2). Por convención de la capa de repositorio
    (cases/repository.py), esta tabla solo recibe INSERT — nunca UPDATE ni
    DELETE. SQLAlchemy no impone esa inmutabilidad a nivel de esquema; la
    garantiza el hecho de que `CaseRepository` es el único punto de acceso
    y jamás expone un método de modificación sobre `Auditoria`.
    """

    __tablename__ = "auditoria"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    caso_id: Mapped[str] = mapped_column(String(36), ForeignKey("caso.id"), nullable=False, index=True)
    campo_modificado: Mapped[str] = mapped_column(String(64), nullable=False)
    valor_anterior: Mapped[str] = mapped_column(Text, nullable=True)
    valor_nuevo: Mapped[str] = mapped_column(Text, nullable=False)
    modificado_por: Mapped[str] = mapped_column(String(128), nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    caso: Mapped["Caso"] = relationship(back_populates="auditoria")
