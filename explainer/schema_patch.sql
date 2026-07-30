-- Parche de esquema: añade la columna explicacion_texto a la tabla caso.
-- Ejecutar UNA sola vez contra la base de datos centinela-casos en Azure SQL,
-- con el mismo usuario administrador AAD que configuró el esquema inicial.
--
-- La columna es nullable intencionalmente: los casos que se abren mientras
-- el explicador está caído quedan con NULL hasta que el explicador se
-- restablece y los procesa (get_cases_pending_explanation devuelve todos
-- los registros con NULL). El estado NULL = "explicación pendiente" es el
-- mecanismo de resiliencia del componente.
--
-- No usa ALTER TABLE ... ADD COLUMN IF NOT EXISTS porque T-SQL (Azure SQL)
-- no soporta esa sintaxis; el bloque IF NOT EXISTS es equivalente.

IF NOT EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID('caso')
      AND name = 'explicacion_texto'
)
BEGIN
    ALTER TABLE caso ADD explicacion_texto NVARCHAR(MAX) NULL;
END;
GO
