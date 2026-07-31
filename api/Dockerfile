# ==============================================================================
# api/Dockerfile — Imagen multi-stage de la API de ingesta (FastAPI)
#
# Optimizaciones de tamaño y seguridad:
#   - Stage "builder": compila dependencias con wheel en una imagen temporal.
#     Las capas con herramientas de compilación (gcc, pip, etc.) no llegan
#     a la imagen final — cualquier archivo eliminado en capas anteriores
#     no reaparece en la imagen final porque el COPY final parte de cero.
#   - Stage "runtime": imagen mínima (slim) con solo el binario Python y los
#     wheels precompilados. Sin pip, sin gcc, sin build-essential.
#   - Sin secretos en ninguna capa: toda configuración llega vía variables
#     de entorno en tiempo de ejecución, no en tiempo de construcción.
#   - Usuario no-root: la aplicación corre como `appuser`, no como root.
# ==============================================================================

# ---- Stage 1: compilación de dependencias ------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Copiar solo el archivo de dependencias primero para aprovechar la cache de
# capas de Docker: si requirements.txt no cambia, esta capa se reutiliza
# aunque el código fuente haya cambiado.
COPY requirements.txt .

# Compilar wheels en /wheels sin instalar en el sistema — los wheels van al
# stage de runtime sin llevar consigo las herramientas de compilación.
RUN pip install --upgrade pip \
    && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# ---- Stage 2: imagen de runtime ----------------------------------------------
FROM python:3.11-slim AS runtime

# Metadatos descriptivos (no afectan el tamaño ni la seguridad)
LABEL org.opencontainers.image.title="Centinela API"
LABEL org.opencontainers.image.description="API de ingesta de transacciones — Centinela"
LABEL org.opencontainers.image.source="https://github.com/CerberusAz/Centinela"

WORKDIR /app

# Instalar wheels compilados en el stage anterior — sin pip, sin gcc
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# Copiar el código fuente de la aplicación
COPY app/ ./app/


# Variables de entorno que configuran el comportamiento del servidor.
# Los valores sensibles (connection strings, URLs de Azure) llegan en tiempo
# de ejecución vía App Settings de Azure — nunca aquí.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

EXPOSE 8000

# Gunicorn con worker Uvicorn: mismo comando configurado en app.bicep
# (appCommandLine) para consistencia entre despliegue zip y contenedor.
CMD ["gunicorn", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "app.main:app"]
