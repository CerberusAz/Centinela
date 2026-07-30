import json
from datetime import datetime
from typing import Any

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient

from app.models.transaction import TransactionIn


class BlobTransactionStorage:
    """
    Persiste cada transacción cruda como un blob JSON individual, usando
    transaction_id como nombre de blob dentro del contenedor configurado
    en `CENTINELA_BLOB_CONTAINER_RAW_TRANSACTIONS` (default: `transacciones`,
    distinto del contenedor de documentos de verificación de identidad de
    la sección 2.10, que es responsabilidad de infraestructura de red/
    almacenamiento, no de este componente).

    Autenticación exclusivamente vía identidad gestionada
    (DefaultAzureCredential resuelve la Managed Identity del App Service en
    Azure; en local resuelve la sesión de `az login`). No se admiten claves
    de cuenta ni connection strings con credenciales embebidas
    (requerimiento 2.10 / 2.6, aplicado aquí por consistencia).
    """

    def __init__(self, account_url: str, container_name: str) -> None:
        self._container_name = container_name
        self._credential = DefaultAzureCredential()
        self._client = BlobServiceClient(account_url=account_url, credential=self._credential)

    async def exists(self, transaction_id: str) -> bool:
        blob_client = self._client.get_blob_client(
            container=self._container_name, blob=self._blob_name(transaction_id)
        )
        return await blob_client.exists()

    async def save(self, transaction: TransactionIn, received_at: datetime) -> None:
        blob_client = self._client.get_blob_client(
            container=self._container_name, blob=self._blob_name(transaction.transaction_id)
        )
        document = {
            "transaction": transaction.model_dump(mode="json"),
            "server_received_at": received_at.isoformat(),
        }
        try:
            # overwrite=False: escritura condicional. Si dos requests concurrentes
            # con el mismo transaction_id pasan el exists()==False a la vez, solo
            # una escritura prospera; la otra falla aquí y se ignora. Ver
            # docs/idempotencia.md para la limitación conocida de este esquema.
            await blob_client.upload_blob(
                json.dumps(document).encode("utf-8"),
                overwrite=False,
            )
        except ResourceExistsError:
            pass

    async def get(self, transaction_id: str) -> dict[str, Any] | None:
        blob_client = self._client.get_blob_client(
            container=self._container_name, blob=self._blob_name(transaction_id)
        )
        try:
            downloader = await blob_client.download_blob()
            data = await downloader.readall()
        except ResourceNotFoundError:
            return None
        return json.loads(data)

    @staticmethod
    def _blob_name(transaction_id: str) -> str:
        return f"{transaction_id}.json"

    async def close(self) -> None:
        await self._client.close()
        await self._credential.close()
