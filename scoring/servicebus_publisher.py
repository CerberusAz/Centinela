"""
Adaptador real de `orchestration.CasePublisher` contra Service Bus (tier
Basic). Mecanismo de GARANTÍA de la sección 2.4 — a diferencia de Event
Grid (usado para el evento de transacción, ver
api/app/messaging/event_grid_publisher.py), Service Bus asegura entrega
at-least-once con dead-lettering nativo (`maxDeliveryCount`, configurado en
infra/bicep/modules/eventing.bicep). Ver docs/mensajeria-semana2.md para la
comparación completa.

Autenticación AAD (`DefaultAzureCredential`, rol de datos "Azure Service
Bus Data Sender"), sin connection string con clave compartida.
"""

import json
import logging

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus import ServiceBusMessage
from azure.servicebus.aio import ServiceBusClient

from rules import ScoringResult

logger = logging.getLogger(__name__)


class ServiceBusCasePublisher:
    def __init__(self, namespace_fqdn: str, queue_name: str) -> None:
        self._queue_name = queue_name
        self._credential = DefaultAzureCredential()
        self._client = ServiceBusClient(fully_qualified_namespace=namespace_fqdn, credential=self._credential)

    async def publish_case(self, transaction_id: str, account_id: str, result: ScoringResult) -> None:
        body = {
            "transaction_id": transaction_id,
            "account_id": account_id,
            "score": result.score,
            "rule_activations": [
                {"rule_id": activation.rule_id, "points": activation.points, "details": activation.details}
                for activation in result.activations
            ],
        }
        message = ServiceBusMessage(json.dumps(body), content_type="application/json")
        async with self._client.get_queue_sender(self._queue_name) as sender:
            await sender.send_messages(message)

        logger.info(
            "Caso publicado en '%s' para transacción %s (score=%d)",
            self._queue_name,
            transaction_id,
            result.score,
        )

    async def close(self) -> None:
        await self._client.close()
        await self._credential.close()