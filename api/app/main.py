import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.services.ingestion import ContractValidationError

logger = logging.getLogger("centinela.api")

app = FastAPI(title="Centinela — API de ingesta de transacciones")
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def handle_payload_shape_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Errores de forma del payload: campos obligatorios ausentes, tipos
    incorrectos, campos no contemplados en el contrato (extra="forbid"),
    JSON malformado, valores fuera de los rangos declarados en el modelo
    (monto <= 0, coordenadas fuera de rango, moneda inválida, etc.).
    Se homologan a 400 (ver docs/codigos-estado.md) y el mensaje no incluye
    traceback ni detalles internos de implementación.
    """
    return JSONResponse(
        status_code=400,
        content={"error": "payload_invalido", "detail": _sanitize_errors(exc.errors())},
    )


@app.exception_handler(ContractValidationError)
async def handle_contract_semantic_error(
    request: Request, exc: ContractValidationError
) -> JSONResponse:
    """Errores de contrato que dependen de configuración o del reloj del servidor."""
    return JSONResponse(status_code=400, content={"error": "payload_invalido", "detail": exc.message})


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """
    Cualquier falla no anticipada (p. ej. backend de almacenamiento no
    disponible). Se registra en el log del servidor con el detalle completo;
    al cliente solo se le devuelve un mensaje genérico, sin exponer
    información interna del sistema.
    """
    logger.exception("Error no controlado al procesar %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "error_interno"})


def _sanitize_errors(errors: list[dict]) -> list[dict]:
    return [
        {"campo": ".".join(str(p) for p in e["loc"] if p != "body"), "motivo": e["msg"]}
        for e in errors
    ]
