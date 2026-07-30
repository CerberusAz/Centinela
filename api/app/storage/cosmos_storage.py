import logging
from datetime import datetime
from typing import Any

from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential

from app.models.transaction import TransactionIn

logger = logging.getLogger(__name__)


class CosmosTransactionStorage:
    """
    Store operativo de transacciones en Cosmos DB (Azure-Semana2.md, sección
    2.1): historial reciente por cuenta que consulta el motor de scoring.
    Partición `/account_id`, consistencia Session, TTL 30 días a nivel
    contenedor (justificación completa en
    docs/justificacion-particionamiento-cosmos.md).

    No es la autoridad de idempotencia ni de `GET /transactions/{id}` — eso
    sigue siendo Blob Storage (ver app/storage/dual_storage.py). `exists()`/
    `get()` existen aquí para cumplir el `Protocol TransactionStorage` y
    para uso standalone/tests, pero al no recibir `account_id` hacen una
    consulta CROSS-PARTICIÓN (cara en RU) — exactamente la consulta que la
    partición por cuenta sacrifica a cambio de optimizar "historial
    reciente de una cuenta". En el flujo real (`DualTransactionStorage`)
    nunca se llaman: Blob resuelve ambas operaciones sin ese costo.

    Autenticación exclusivamente por identidad gestionada
    (`DefaultAzureCredential` + RBAC de datos de Cosmos, sin claves — mismo
    principio que `blob_storage.py`).
    """

    def __init__(self, account_url: str, database_name: str, container_name: str) -> None:
        self._container_name = container_name
        self._database_name = database_name
        self._credential = DefaultAzureCredential()
        self._client = CosmosClient(url=account_url, credential=self._credential)

    def _container(self):
        return self._client.get_database_client(self._database_name).get_container_client(
            self._container_name
        )

    async def exists(self, transaction_id: str) -> bool:
        return await self.get(transaction_id) is not None

    async def get(self, transaction_id: str) -> dict[str, Any] | None:
        container = self._container()
        query = "SELECT * FROM c WHERE c.transaction_id = @transaction_id"
        parameters = [{"name": "@transaction_id", "value": transaction_id}]
        items = [
            item
            async for item in container.query_items(
                query=query, parameters=parameters, enable_cross_partition_query=True
            )
        ]
        return items[0] if items else None

    async def save(self, transaction: TransactionIn, received_at: datetime) -> None:
        container = self._container()
        document = {
            "id": transaction.transaction_id,
            "account_id": transaction.account_id,
            "transaction_id": transaction.transaction_id,
            "amount_minor_units": transaction.amount_minor_units,
            "currency": transaction.currency,
            "server_received_at": received_at.isoformat(),
            "location": transaction.location.model_dump(),
            "merchant": transaction.merchant.model_dump(),
            # El motor de scoring (semana 2, componente separado) completa
            # estos dos campos con un upsert posterior al mismo documento
            # (Azure-Semana2.md 2.3, paso 5: "persistir el score ... junto
            # a la transacción").
            "score": None,
            "rule_activations": [],
        }
        await container.upsert_item(document)

    async def close(self) -> None:
        await self._client.close()
        await self._credential.close()