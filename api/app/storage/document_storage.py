import uuid
from datetime import datetime, timezone
from typing import Any

from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient


# Tipos de archivo aceptados para documentos de verificación de identidad.
# La detección es por magic bytes (contenido real), no por extensión (sección 2.10).
# Un archivo .pdf renombrado a .jpg se detecta correctamente como PDF.
_ALLOWED_MAGIC: dict[bytes, str] = {
    b"%PDF": "pdf",
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG": "png",
}
_MAGIC_MAX_BYTES = 4  # Los magic bytes más largos tienen 4 bytes


class DocumentTypeError(Exception):
    """El archivo no corresponde a ningún tipo permitido según sus magic bytes."""


class DocumentSizeError(Exception):
    """El archivo supera el tamaño máximo configurado."""


def _detect_content_type(data: bytes) -> str:
    """
    Detecta el tipo de archivo inspeccionando los primeros bytes del contenido
    (magic bytes), no la extensión declarada por el usuario.

    Tipos aceptados: PDF, JPEG, PNG.
    Cualquier otro tipo lanza DocumentTypeError.

    Sección 2.10: "Validación de tipo de archivo por contenido real, no por extensión."
    """
    header = data[:_MAGIC_MAX_BYTES]
    for magic, ext in _ALLOWED_MAGIC.items():
        if header[: len(magic)] == magic:
            return ext
    raise DocumentTypeError(
        "Tipo de archivo no permitido. Se aceptan únicamente: PDF, JPEG, PNG."
    )


def _generate_blob_name(ext: str) -> str:
    """
    Genera el nombre del blob en destino.

    Formato: {uuid4}/{timestamp_utc}.{ext}

    El nombre lo genera el sistema — no se usa el nombre de archivo proporcionado
    por el usuario (sección 2.10: "El nombre del objeto en destino lo genera el
    sistema. No se utiliza el nombre de archivo proporcionado por el usuario.").

    El UUID v4 como prefijo de "directorio" agrupa los documentos de un mismo
    caso de carga y evita colisiones en el contenedor, incluso ante cargas
    concurrentes. El timestamp permite ordenar cronológicamente dentro de un grupo.
    """
    document_uuid = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{document_uuid}/{timestamp}.{ext}"


class BlobDocumentStorage:
    """
    Almacena documentos de verificación de identidad en Azure Blob Storage.

    Implementa los requisitos de la sección 2.10:
    - Autenticación mediante identidad gestionada (DefaultAzureCredential).
    - Validación de tipo de archivo por contenido real (magic bytes).
    - Límite de tamaño máximo configurable.
    - Nombre del objeto generado por el sistema.

    No se admiten claves de acceso ni connection strings (requerimiento 2.6/2.10).
    """

    def __init__(
        self,
        account_url: str,
        container_name: str,
        max_size_bytes: int,
    ) -> None:
        self._container_name = container_name
        self._max_size_bytes = max_size_bytes
        self._credential = DefaultAzureCredential()
        self._client = BlobServiceClient(
            account_url=account_url, credential=self._credential
        )

    async def upload(self, file_bytes: bytes, original_filename: str) -> dict[str, Any]:
        """
        Valida y carga un documento de verificación de identidad.

        Args:
            file_bytes: contenido completo del archivo.
            original_filename: nombre original declarado por el usuario (solo
                se usa para logging/trazabilidad, nunca como nombre de blob).

        Returns:
            Diccionario con metadatos del documento subido:
            { document_id, blob_name, content_type, size_bytes, uploaded_at }

        Raises:
            DocumentSizeError: si el archivo supera max_size_bytes.
            DocumentTypeError: si el tipo de archivo no está en la lista de permitidos.
        """
        # 1. Verificar tamaño antes de inspeccionar el contenido
        if len(file_bytes) > self._max_size_bytes:
            raise DocumentSizeError(
                f"El archivo supera el tamaño máximo permitido "
                f"({self._max_size_bytes} bytes)."
            )

        # 2. Detectar tipo por contenido real (magic bytes), no por extensión
        ext = _detect_content_type(file_bytes)

        # 3. Generar nombre de blob — el sistema lo define, no el usuario
        blob_name = _generate_blob_name(ext)
        document_id = blob_name.split("/")[0]  # El UUID del prefijo de directorio

        uploaded_at = datetime.now(timezone.utc)

        blob_client = self._client.get_blob_client(
            container=self._container_name, blob=blob_name
        )
        await blob_client.upload_blob(
            file_bytes,
            overwrite=False,
            metadata={
                # Metadatos de trazabilidad — el nombre de archivo original
                # se guarda como metadata del blob, no como nombre del blob.
                "original_filename": original_filename[:256],  # Truncar para evitar headers largos
                "uploaded_at": uploaded_at.isoformat(),
            },
        )

        return {
            "document_id": document_id,
            "blob_name": blob_name,
            "content_type": ext,
            "size_bytes": len(file_bytes),
            "uploaded_at": uploaded_at.isoformat(),
        }

    async def close(self) -> None:
        await self._client.close()
        await self._credential.close()
