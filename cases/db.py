"""
Conexión al almacén de casos.

SQLite en memoria: usado en tests y desarrollo local, sin ninguna
dependencia de Azure — permite probar cases/repository.py de punta a punta
en este entorno.

Azure SQL: autenticación exclusivamente vía identidad gestionada
(DefaultAzureCredential), sin usuario/contraseña ni connection string con
credenciales embebidas (mismo principio que api/app/storage/blob_storage.py
y scoring/cosmos_repository.py). Esta ruta no se puede ejercer desde este
entorno de desarrollo (sin red hacia Azure) — además requiere un paso
manual previo contra la base real, no expresable en Bicep: `CREATE USER
[nombre-managed-identity] FROM EXTERNAL PROVIDER` (ver
docs/decisiones-arquitectura.md, ADR sobre el almacén de casos).
"""

import struct

from models import ESTADOS_INICIALES, Base, Estado
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_SQL_COPT_SS_ACCESS_TOKEN = 1256


def create_sqlite_engine(url: str = "sqlite:///:memory:") -> Engine:
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_estados(session)
        session.commit()
    return engine


def seed_estados(session: Session) -> None:
    for codigo, descripcion in ESTADOS_INICIALES:
        if session.get(Estado, codigo) is None:
            session.add(Estado(codigo=codigo, descripcion=descripcion))


def create_azure_sql_engine(server: str, database: str) -> Engine:
    """
    server: p. ej. 'sql-trial-dev-weu-003.database.windows.net'
    database: p. ej. 'centinela-casos'

    No crea el esquema (a diferencia de create_sqlite_engine): en Azure SQL
    real el esquema se aplica una sola vez con cases/schema.sql, fuera del
    ciclo de vida de la Function.
    """
    from azure.identity import DefaultAzureCredential  # import local: solo aplica a esta ruta

    connection_string = (
        f"mssql+pyodbc://@{server}/{database}"
        "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
    )
    credential = DefaultAzureCredential()
    engine = create_engine(connection_string, future=True)

    @event.listens_for(engine, "do_connect")
    def _provide_aad_token(dialect, conn_rec, cargs, cparams):
        token = credential.get_token("https://database.windows.net/.default").token.encode("utf-16-le")
        token_struct = struct.pack(f"<I{len(token)}s", len(token), token)
        cparams["attrs_before"] = {_SQL_COPT_SS_ACCESS_TOKEN: token_struct}

    return engine


def create_session(engine: Engine) -> Session:
    factory = sessionmaker(bind=engine, future=True)
    return factory()
