# ==============================================================================
# cases/Dockerfile — Imagen de la Function de creación de casos (Azure Functions v4)
#
# Mismo patrón que scoring/Dockerfile: imagen base oficial de Azure Functions
# más las dependencias específicas de este componente (SQLAlchemy, pyodbc).
#
# Nota sobre pyodbc y el driver ODBC de Microsoft:
#   La imagen base de Azure Functions (Debian/Ubuntu) incluye las librerías
#   de sistema necesarias para el driver ODBC de Microsoft. Se instala
#   `msodbcsql18` desde el repositorio oficial de Microsoft para que pyodbc
#   pueda conectarse a Azure SQL con autenticación AAD.
#   Esto requiere aceptar la licencia de Microsoft ODBC Driver (EULA),
#   que se acepta con ACCEPT_EULA=Y en la variable de entorno de apt.
#
# Sin secretos: la cadena de conexión a SQL llega vía App Settings en tiempo
# de ejecución. La imagen no contiene ningún token, clave ni URL.
# ==============================================================================

# ---- Stage 1: compilación de dependencias Python -----------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .

RUN pip install --upgrade pip \
    && grep -v "^azure-functions" requirements.txt > requirements-no-func.txt \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements-no-func.txt


# ---- Stage 2: imagen de runtime con host de Azure Functions y ODBC -----------
FROM mcr.microsoft.com/azure-functions/python:4-python3.11 AS runtime

LABEL org.opencontainers.image.title="Centinela Cases Function"
LABEL org.opencontainers.image.description="Function de creación de casos — Centinela"
LABEL org.opencontainers.image.source="https://github.com/CerberusAz/Centinela"

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Instalar el driver ODBC de Microsoft para Azure SQL (msodbcsql18).
# Esto es necesario para que pyodbc pueda autenticarse contra Azure SQL
# con un token AAD (DefaultAzureCredential + SQL_COPT_SS_ACCESS_TOKEN).
# La licencia EULA de Microsoft ODBC Driver se acepta con ACCEPT_EULA=Y.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg2 \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc \
       | gpg --dearmor > /usr/share/keyrings/microsoft-prod.gpg \
    && curl -sSL https://packages.microsoft.com/config/debian/12/prod.list \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/site/wwwroot

# Instalar dependencias Python precompiladas
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels \
        -r <(sed 's/#.*//' requirements.txt \
             | grep -v "^azure-functions" \
             | grep -v "^pyodbc" \
             | grep -v '^[[:space:]]*$') \
    && pip install --no-cache-dir pyodbc \
    && rm -rf /wheels

# Copiar código fuente
COPY function_app.py \
     config.py \
     db.py \
     models.py \
     repository.py \
     host.json \
     ./
