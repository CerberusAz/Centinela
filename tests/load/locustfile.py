import random
import uuid
from datetime import datetime, timezone

from locust import HttpUser, between, task


class CentinelaUser(HttpUser):
    """
    Simula tráfico sintético hacia la API de ingesta de Centinela.
    Permite demostrar el comportamiento de auto-escalado (KEDA / Azure App Service / Functions)
    y generar carga suficiente para las pruebas de observabilidad en App Insights.
    """

    # Tiempo de espera aleatorio entre peticiones de un mismo usuario virtual
    wait_time = between(0.1, 0.5)

    @task
    def ingest_transaction(self):
        """Genera una transacción sintética válida y la envía a la API."""
        
        # Generar un UUID v4 para idempotencia
        transaction_id = str(uuid.uuid4())
        
        # Simular una cantidad acotada de cuentas para generar historial (importante para las reglas de scoring)
        account_id = f"acc_{random.randint(1, 1000):04d}"
        
        # Monto aleatorio entre $1.00 y $10,000.00
        amount_minor_units = random.randint(100, 1000000)
        
        payload = {
            "transaction_id": transaction_id,
            "account_id": account_id,
            "amount_minor_units": amount_minor_units,
            "currency": "USD",
            "client_timestamp": datetime.now(timezone.utc).isoformat(),
            "location": {
                "latitude": round(random.uniform(-90.0, 90.0), 4),
                "longitude": round(random.uniform(-180.0, 180.0), 4)
            },
            "merchant": {
                "merchant_id": f"m_{random.randint(1, 500)}",
                # Insertamos aleatoriamente categorías de riesgo configuradas en el motor
                "category": random.choice(
                    ["retail", "restaurant", "online", "grocery", "gambling", "crypto_exchange"]
                )
            }
        }

        # POST /transactions (se asume que --host apunta a la Web App)
        with self.client.post("/transactions", json=payload, catch_response=True) as response:
            if response.status_code == 201:
                response.success()
            elif response.status_code == 429:
                response.failure("Rate Limit (HTTP 429)")
            else:
                response.failure(f"Error HTTP {response.status_code}: {response.text}")
