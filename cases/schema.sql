-- Esquema del almacén de casos (Azure-Semana2.md, sección 2.2).
-- DDL T-SQL para ejecución manual contra Azure SQL real, equivalente al
-- esquema que cases/models.py genera automáticamente contra SQLite en
-- tests/desarrollo local. Mantener ambos sincronizados a mano si el
-- modelo cambia -- no hay generación automática entre los dos en esta
-- semana (fuera de alcance: migraciones formales).

CREATE TABLE estado (
    codigo          NVARCHAR(32)  NOT NULL PRIMARY KEY,
    descripcion     NVARCHAR(256) NOT NULL
);

CREATE TABLE caso (
    id                      NVARCHAR(36)   NOT NULL PRIMARY KEY,
    transaction_id          NVARCHAR(36)   NOT NULL,
    account_id              NVARCHAR(128)  NOT NULL,
    score                   INT            NOT NULL,
    reglas_activadas_json   NVARCHAR(MAX)  NOT NULL,
    estado_codigo           NVARCHAR(32)   NOT NULL DEFAULT 'abierto',
    fecha_apertura          DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
    CONSTRAINT uq_caso_transaction_id UNIQUE (transaction_id),
    CONSTRAINT fk_caso_estado FOREIGN KEY (estado_codigo) REFERENCES estado(codigo)
);
CREATE INDEX ix_caso_account_id ON caso(account_id);

CREATE TABLE asignacion (
    id                  NVARCHAR(36)   NOT NULL PRIMARY KEY,
    caso_id             NVARCHAR(36)   NOT NULL,
    analista            NVARCHAR(128)  NOT NULL,
    fecha_asignacion    DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
    CONSTRAINT fk_asignacion_caso FOREIGN KEY (caso_id) REFERENCES caso(id)
);
CREATE INDEX ix_asignacion_caso_id ON asignacion(caso_id);

CREATE TABLE resolucion (
    id              NVARCHAR(36)   NOT NULL PRIMARY KEY,
    caso_id         NVARCHAR(36)   NOT NULL,
    decision        NVARCHAR(64)   NOT NULL,
    analista        NVARCHAR(128)  NOT NULL,
    fecha           DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
    observaciones   NVARCHAR(MAX)  NULL,
    CONSTRAINT uq_resolucion_caso_id UNIQUE (caso_id),
    CONSTRAINT fk_resolucion_caso FOREIGN KEY (caso_id) REFERENCES caso(id)
);

CREATE TABLE auditoria (
    id                  NVARCHAR(36)   NOT NULL PRIMARY KEY,
    caso_id             NVARCHAR(36)   NOT NULL,
    campo_modificado    NVARCHAR(64)   NOT NULL,
    valor_anterior      NVARCHAR(MAX)  NULL,
    valor_nuevo         NVARCHAR(MAX)  NOT NULL,
    modificado_por      NVARCHAR(128)  NOT NULL,
    fecha               DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
    CONSTRAINT fk_auditoria_caso FOREIGN KEY (caso_id) REFERENCES caso(id)
);
CREATE INDEX ix_auditoria_caso_id ON auditoria(caso_id);

INSERT INTO estado (codigo, descripcion) VALUES
    (N'abierto',  N'Caso recién creado, sin analista asignado'),
    (N'asignado', N'Caso asignado a un analista, en análisis'),
    (N'resuelto', N'Caso con decisión final registrada');

-- Inmutabilidad de `auditoria`: se aplica por convención de la capa de
-- repositorio (cases/repository.py), que nunca expone UPDATE/DELETE sobre
-- esta tabla. Para reforzarlo a nivel de base de datos (recomendado antes
-- de ir a producción real), revocar permisos UPDATE/DELETE sobre esta
-- tabla al usuario/rol de la Function de casos, dejando solo INSERT/SELECT:
--
-- DENY UPDATE, DELETE ON auditoria TO [nombre-managed-identity-cases-function];