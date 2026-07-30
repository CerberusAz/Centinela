"""
Adaptador real de `orchestration.HistoryRepository` contra Cosmos DB.
Autenticación exclusivamente por identidad gestionada
(`DefaultAzureCredential` + rol de datos "Cosmos DB Built-in Data
Contributor"), sin claves — mismo principio que el resto del proyecto.
"""

import logging
from datetime import datetime
from typing import Any

from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential

from rules import ScoringResult

logger = logging.getLogger(__name__)


def _parse_history_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "transaction_id": item["transaction_id"],
        "account_id": item["account_id"],
        "amount_minor_units": item["amount_minor_units"],
        "server_received_at": datetime.fromisoformat(item["server_received_at"]),
        "location": item["location"],
        "merchant": item["merchant"],
    }


class CosmosHistoryRepository:
    def __init__(self, account_url: str, database_name: str, container_name: str) -> None:
        self._container_name = container_name
        self._database_name = database_name
        self._credential = DefaultAzureCredential()
        self._client = CosmosClient(url=account_url, credential=self._credential)

    def _container(self):
        return self._client.get_database_client(self._database_name).get_container_client(
            self._container_name
        )

    async def query_recent_history(
        self, account_id: str, exclude_transaction_id: str, since: datetime
    ) -> list[dict[str, Any]]:
        """
        Consulta de PARTICIÓN ÚNICA (`partition_key=account_id`) — la que
        la clave `/account_id` está diseñada para optimizar
        (docs/justificacion-particionamiento-cosmos.md). No hace fan-out
        entre particiones.
        """
        container = self._container()
        query = (
            "SELECT * FROM c WHERE c.account_id = @account_id "
            "AND c.transaction_id != @exclude_id "
            "AND c.server_received_at >= @since"
        )
        parameters = [
            {"name": "@account_id", "value": account_id},
            {"name": "@exclude_id", "value": exclude_transaction_id},
            {"name": "@since", "value": since.isoformat()},
        ]

        items: list[dict[str, Any]] = []
        query_iterable = container.query_items(
            query=query, parameters=parameters, partition_key=account_id
        )
        async for item in query_iterable:
            items.append(_parse_history_item(item))

        # Evidencia para el criterio de aceptación "demostrable mediante la
        # métrica de consumo de la consulta" (Azure-Semana2.md, sección 4).
        # La forma exacta de leer el cargo en RU depende de la versión del
        # SDK y no se pudo verificar contra una cuenta Cosmos real en este
        # entorno de desarrollo — best-effort, documentado como limitación.
        request_charge = None
        try:
            request_charge = query_iterable.response_headers.get("x-ms-request-charge")
        except AttributeError:
            pass
        logger.info(
            "Historial account_id=%s: %d transacciones (RU=%s)",
            account_id,
            len(items),
            request_charge,
        )
        return items

    async def persist_score(self, transaction_id: str, account_id: str, result: ScoringResult) -> None:
        """
        Sección 2.3, paso 5: "persistir el score y el detalle de las reglas
        activadas junto a la transacción" — se actualiza el MISMO documento
        que la API escribió (mismo id/partición), no un registro aparte.
        """
        container = self._container()
        document = await container.read_item(item=transaction_id, partition_key=account_id)
        document["score"] = result.score
        document["rule_activations"] = [
            {"rule_id": activation.rule_id, "points": activation.points, "details": activation.details}
            for activation in result.activations
        ]
        await container.replace_item(item=document, body=document)

    async def close(self) -> None:
        await self._client.close()
        await self._credential.close()