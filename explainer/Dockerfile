# ==============================================================================
# explainer/Dockerfile — Imagen de la Function del explicador (Azure Functions v4)
#
# Comparte la base oficial de Azure Functions con Python 3.11.
# Incluye el driver ODBC de Microsoft (msodbcsql18) porque utiliza SQLAlchemy
# y pyodbc para conectarse a la misma base de datos Azure SQL que el componente
# de casos, autenticando con Managed Identity.
# ==============================================================================

FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .

RUN pip install --upgrade pip \
    && grep -v "^azure-functions" requirements.txt > requirements-no-func.txt \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements-no-func.txt


FROM mcr.microsoft.com/azure-functions/python:4-python3.11 AS runtime

LABEL org.opencontainers.image.title="Centinela Explainer Function"
LABEL org.opencontainers.image.description="Function explicadora de casos — Centinela"

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Instalar driver ODBC (requerido por pyodbc contra Azure SQL)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg2 \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft-prod.gpg \
    && curl -sSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/site/wwwroot

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels \
        -r <(sed 's/#.*//' requirements.txt \
             | grep -v "^azure-functions" \
             | grep -v "^pyodbc" \
             | grep -v '^[[:space:]]*$') \
    && pip install --no-cache-dir pyodbc \
    && rm -rf /wheels

# Copiar el modelo compartido (en CI/CD esto se podría resolver con un paquete común,
# pero para mantener el mono-repo simple, asumimos que models.py se copia aquí).
# En realidad, models.py y db.py de cases/ se deben copiar a este directorio
# antes de hacer build, o bien usamos un path relativo en docker build.
# Para evitar complejidad de build context, requerimos que el script de build copie
# cases/models.py y cases/db.py a explainer/ o los copiamos explícitamente en el pipeline.
COPY function_app.py \
     config.py \
     explainer.py \
     repository.py \
     models.py \
     db.py \
     host.json \
     ./
