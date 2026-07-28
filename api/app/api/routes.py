from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.models.transaction import TransactionIn
from app.services.ingestion import IngestionService, get_ingestion_service

router = APIRouter()


@router.post("/transactions", status_code=status.HTTP_201_CREATED)
async def ingest_transaction(
    payload: TransactionIn,
    service: IngestionService = Depends(get_ingestion_service),
) -> JSONResponse:
    """
    Capa HTTP: no contiene lógica de negocio. `payload: TransactionIn` ya
    aplicó la validación de forma del contrato (FastAPI/Pydantic) antes de
    llegar aquí; la validación semántica restante y la persistencia se
    delegan a IngestionService.
    """
    result = await service.ingest(payload)
    return JSONResponse(status_code=result.status_code, content=result.body)


@router.get("/transactions/{transaction_id}")
async def get_transaction(
    transaction_id: str,
    service: IngestionService = Depends(get_ingestion_service),
) -> JSONResponse:
    document = await service.get(transaction_id)
    if document is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "transaccion_no_encontrada"},
        )
    return JSONResponse(status_code=status.HTTP_200_OK, content=document)
