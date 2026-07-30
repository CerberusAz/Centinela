"""
Configuración externalizada del motor de scoring (mismo principio que
api/app/core/config.py: prefijo de entorno, sin valores embebidos en
código). El umbral y los puntos por regla se leen de variables de entorno
CENTINELA_SCORING_* — en Azure, App Settings de la Function App — cuyo
cambio no requiere un nuevo despliegue de código (Azure-Semana2.md,
entregable 6: "modificable sin redespliegue").
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from rules import ScoringConfig


def _parse_csv(value: str) -> frozenset[str]:
    return frozenset(item.strip() for item in value.split(",") if item.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CENTINELA_SCORING_", env_file=".env", extra="ignore")

    # Cosmos DB — historial de transacciones (app/storage/cosmos_storage.py
    # escribe el mismo contenedor desde la API).
    cosmos_account_url: str
    cosmos_database_name: str = "centinela"
    cosmos_container_transactions: str = "transactions"

    # Service Bus — cola de casos marcados (docs/mensajeria-semana2.md).
    servicebus_namespace_fqdn: str
    servicebus_queue_casos: str = "casos-marcados"

    # Cuántos días de historial consultar en cada evaluación (ventana de
    # CONSULTA, distinta del TTL de 30 días del contenedor — ver
    # docs/justificacion-particionamiento-cosmos.md).
    history_lookback_days: int = 30

    # Umbral de apertura de caso y puntos/ventanas por regla — justificación
    # de los valores por defecto en docs/umbral-scoring.md.
    score_threshold: int = 100

    velocity_window_seconds: int = 300
    velocity_max_count: int = 5
    velocity_points: int = 30

    amount_min_history_points: int = 3
    amount_stddev_multiplier: float = 3.0
    amount_points: int = 40

    geo_max_speed_kmh: float = 900.0
    geo_points: int = 50

    risky_categories_csv: str = "gambling,crypto_exchange,money_transfer"
    risky_merchant_ids_csv: str = ""
    risky_merchant_points: int = 25

    def to_scoring_config(self) -> ScoringConfig:
        return ScoringConfig(
            velocity_window_seconds=self.velocity_window_seconds,
            velocity_max_count=self.velocity_max_count,
            velocity_points=self.velocity_points,
            amount_min_history_points=self.amount_min_history_points,
            amount_stddev_multiplier=self.amount_stddev_multiplier,
            amount_points=self.amount_points,
            geo_max_speed_kmh=self.geo_max_speed_kmh,
            geo_points=self.geo_points,
            risky_categories=_parse_csv(self.risky_categories_csv),
            risky_merchant_ids=_parse_csv(self.risky_merchant_ids_csv),
            risky_merchant_points=self.risky_merchant_points,
            score_threshold=self.score_threshold,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()