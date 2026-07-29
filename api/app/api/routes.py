from fastapi import APIRouter, Depends, UploadFile, status
from fastapi.responses import JSONResponse

from app.core.config import Settings, StorageBackend, get_settings
from app.models.transaction import TransactionIn
from app.services.ingestion import IngestionService, get_ingestion_service
from app.storage.document_storage import (
    BlobDocumentStorage,
    DocumentSizeError,
    DocumentTypeError,
)

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


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_identity_document(
    file: UploadFile,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """
    Carga un documento de verificación de identidad al contenedor
    `identity-documents` de Azure Blob Storage (sección 2.10).

    Requisitos aplicados:
    - Autenticación mediante identidad gestionada (DefaultAzureCredential).
    - Validación de tipo de archivo por contenido real (magic bytes), no extensión.
    - Límite de tamaño máximo (CENTINELA_MAX_DOCUMENT_SIZE_BYTES, default 10 MB).
    - El nombre del blob lo genera el sistema — no se usa el nombre del usuario.

    Tipos de archivo aceptados: PDF, JPEG, PNG.

    Respuestas:
    - 201: documento cargado, con document_id, blob_name, content_type, size_bytes.
    - 400: tipo de archivo no permitido o tamaño excedido.
    - 503: backend de almacenamiento no disponible (requiere CENTINELA_STORAGE_BACKEND=blob).
    """
    # El endpoint de documentos requiere el backend blob — no tiene sentido
    # cargar documentos a memoria en producción.
    if settings.storage_backend != StorageBackend.BLOB or not settings.blob_account_url:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": "almacenamiento_no_disponible",
                "detail": (
                    "La carga de documentos requiere CENTINELA_STORAGE_BACKEND=blob "
                    "y CENTINELA_BLOB_ACCOUNT_URL configurados."
                ),
            },
        )

    file_bytes = await file.read()
    original_filename = file.filename or "sin_nombre"

    storage = BlobDocumentStorage(
        account_url=settings.blob_account_url,
        container_name=settings.identity_blob_container,
        max_size_bytes=settings.max_document_size_bytes,
    )

    try:
        result = await storage.upload(file_bytes, original_filename)
    except DocumentSizeError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "archivo_demasiado_grande", "detail": str(exc)},
        )
    except DocumentTypeError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "tipo_archivo_no_permitido", "detail": str(exc)},
        )
    finally:
        await storage.close()

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"status": "accepted", **result},
    )
