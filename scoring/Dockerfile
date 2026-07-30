# ==============================================================================
# scoring/Dockerfile — Imagen del motor de scoring (Azure Functions v4, Python)
#
# Azure Functions en contenedor requiere la imagen base oficial de Microsoft
# (mcr.microsoft.com/azure-functions/python) que incluye el host de Functions
# preinstalado. No se puede usar python:slim directamente porque el host de
# Functions no es un binario que se pueda instalar con pip.
#
# Optimizaciones de tamaño y seguridad:
#   - Stage "builder": compila las dependencias propias del proyecto en wheels.
#     Las herramientas de compilación no llegan a la imagen final.
#   - Stage "runtime": parte de la imagen oficial de Azure Functions (ya incluye
#     el host) e instala solo los wheels precompilados.
#   - Sin secretos: toda configuración llega vía App Settings de Azure en
#     tiempo de ejecución. La imagen no contiene URLs, claves ni tokens.
#   - La imagen base de Functions corre con el usuario `app` por defecto —
#     no se corre como root.
# ==============================================================================

# ---- Stage 1: compilación de dependencias ------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .

# Excluir azure-functions del build de wheels: la imagen base de Functions ya
# lo incluye; incluirlo duplicaría la capa y podría generar conflictos de versión.
RUN pip install --upgrade pip \
    && grep -v "^azure-functions" requirements.txt > requirements-no-func.txt \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements-no-func.txt


# ---- Stage 2: imagen de runtime con host de Azure Functions ------------------
FROM mcr.microsoft.com/azure-functions/python:4-python3.11 AS runtime

LABEL org.opencontainers.image.title="Centinela Scoring Function"
LABEL org.opencontainers.image.description="Motor de scoring de transacciones — Centinela"
LABEL org.opencontainers.image.source="https://github.com/CerberusAz/Centinela"

# AzureWebJobsScriptRoot: directorio donde el host de Functions busca el código.
# La variable AzureFunctionsJobHost__Logging__Console__IsEnabled activa los
# logs en stdout para que Azure los capture correctamente en contenedor.
ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /home/site/wwwroot

# Instalar dependencias precompiladas desde el stage builder
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels \
        $(grep -v "^azure-functions" requirements.txt | tr '\n' ' ') \
    && rm -rf /wheels

# Copiar código fuente del motor de scoring
# El host de Functions descubre las funciones a partir de function_app.py
COPY function_app.py \
     config.py \
     orchestration.py \
     rules.py \
     cosmos_repository.py \
     servicebus_publisher.py \
     host.json \
     ./
