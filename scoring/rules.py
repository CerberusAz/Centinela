"""
Las cuatro reglas de detección de fraude (Azure-Semana2.md, sección 2.3).

Módulo puro: no importa nada de Azure ni hace I/O. Recibe la transacción
actual, el historial reciente de la cuenta (ya resuelto por quien llama
—cosmos_repository.py en producción, una lista en memoria en los tests—) y
la configuración de umbrales, y devuelve qué reglas se activaron con los
valores concretos que las activaron (Azure-Semana2.md 2.3: "cada regla
activada debe persistir los datos concretos que la activaron, no
únicamente su identificador").

Formato esperado de `transaction` y de cada elemento de `history`:
    {
        "transaction_id": str,
        "account_id": str,
        "amount_minor_units": int,
        "server_received_at": datetime (tz-aware),
        "location": {"latitude": float, "longitude": float},
        "merchant": {"merchant_id": str, "category": str},
    }
`server_received_at` es el instante asignado por el servidor al persistir
(no `client_timestamp`, que no es autoritativo — ver contrato de
transacción de semana 1).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Any

EARTH_RADIUS_KM = 6371.0

RULE_VELOCITY = "velocidad"
RULE_MONTO_ATIPICO = "monto_atipico"
RULE_GEO_IMPOSIBLE = "geo_imposible"
RULE_COMERCIO_RIESGO = "comercio_riesgo"


@dataclass(frozen=True)
class ScoringConfig:
    """
    Umbrales del motor de scoring. `scoring/config.py` construye esta
    instancia a partir de variables de entorno (CENTINELA_SCORING_*) — este
    dataclass en sí no depende de configuración externa, así los tests
    pueden instanciarlo directamente con valores explícitos.
    """

    # Velocidad: ventana corta y cantidad máxima de transacciones toleradas
    # dentro de ella (incluyendo la transacción actual).
    velocity_window_seconds: int = 300  # 5 minutos
    velocity_max_count: int = 5
    velocity_points: int = 30

    # Monto atípico: se requiere un mínimo de historial para tener una
    # línea base significativa; por debajo de ese mínimo la regla no se
    # evalúa (no hay suficiente comportamiento histórico que desviar).
    amount_min_history_points: int = 3
    amount_stddev_multiplier: float = 3.0
    amount_points: int = 40

    # Geo-imposible: velocidad de desplazamiento implícita máxima
    # plausible entre dos transacciones consecutivas de la misma cuenta.
    # 900 km/h ~ velocidad de crucero de un vuelo comercial: cualquier
    # desplazamiento implícito mayor no es alcanzable por un mismo titular
    # entre dos transacciones físicas.
    geo_max_speed_kmh: float = 900.0
    geo_points: int = 50

    # Comercio de riesgo: listas configurables de categorías/comercios
    # marcados. Valores por defecto ilustrativos — en producción los
    # define el equipo de cumplimiento, no el motor de scoring.
    risky_categories: frozenset[str] = field(
        default_factory=lambda: frozenset({"gambling", "crypto_exchange", "money_transfer"})
    )
    risky_merchant_ids: frozenset[str] = field(default_factory=frozenset)
    risky_merchant_points: int = 25

    # Umbral de apertura de caso (sección 2.3: "si el score supera el
    # umbral, publicar un mensaje de apertura de caso"). Justificación del
    # valor por defecto en docs/umbral-scoring.md.
    score_threshold: int = 100


@dataclass(frozen=True)
class RuleActivation:
    rule_id: str
    points: int
    details: dict[str, Any]


@dataclass(frozen=True)
class ScoringResult:
    score: int
    activations: list[RuleActivation]

    @property
    def rule_ids(self) -> list[str]:
        return [activation.rule_id for activation in self.activations]

    def exceeds_threshold(self, config: ScoringConfig) -> bool:
        return self.score >= config.score_threshold


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en línea recta entre dos coordenadas, en kilómetros."""
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, (lat1, lon1, lat2, lon2))
    d_lat = lat2_r - lat1_r
    d_lon = lon2_r - lon1_r
    a = sin(d_lat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def rule_velocity(
    transaction: dict[str, Any], history: list[dict[str, Any]], config: ScoringConfig
) -> RuleActivation | None:
    current_time: datetime = transaction["server_received_at"]
    window_start = current_time - timedelta(seconds=config.velocity_window_seconds)

    in_window = [
        item
        for item in history
        if window_start <= item["server_received_at"] <= current_time
    ]
    # La transacción actual cuenta como parte de la ventana.
    count = len(in_window) + 1

    if count < config.velocity_max_count:
        return None

    return RuleActivation(
        rule_id=RULE_VELOCITY,
        points=config.velocity_points,
        details={
            "transaction_count": count,
            "window_seconds": config.velocity_window_seconds,
            "max_allowed": config.velocity_max_count,
        },
    )


def rule_monto_atipico(
    transaction: dict[str, Any], history: list[dict[str, Any]], config: ScoringConfig
) -> RuleActivation | None:
    if len(history) < config.amount_min_history_points:
        return None

    amounts = [item["amount_minor_units"] for item in history]
    mean = sum(amounts) / len(amounts)
    variance = sum((amount - mean) ** 2 for amount in amounts) / len(amounts)
    stddev = sqrt(variance)

    current_amount = transaction["amount_minor_units"]

    if stddev == 0:
        # Historial perfectamente uniforme: cualquier monto distinto (por
        # encima del único valor observado) ya es una desviación, no hay
        # varianza contra la cual medir un múltiplo de stddev.
        threshold = mean
    else:
        threshold = mean + config.amount_stddev_multiplier * stddev

    if current_amount <= threshold:
        return None

    return RuleActivation(
        rule_id=RULE_MONTO_ATIPICO,
        points=config.amount_points,
        details={
            "observed_amount_minor_units": current_amount,
            "historical_mean_minor_units": round(mean, 2),
            "historical_stddev_minor_units": round(stddev, 2),
            "stddev_multiplier": config.amount_stddev_multiplier,
            "history_size": len(amounts),
        },
    )


def rule_geo_imposible(
    transaction: dict[str, Any], history: list[dict[str, Any]], config: ScoringConfig
) -> RuleActivation | None:
    if not history:
        return None

    previous = max(history, key=lambda item: item["server_received_at"])

    current_time: datetime = transaction["server_received_at"]
    previous_time: datetime = previous["server_received_at"]
    elapsed_seconds = (current_time - previous_time).total_seconds()

    distance_km = _haversine_km(
        previous["location"]["latitude"],
        previous["location"]["longitude"],
        transaction["location"]["latitude"],
        transaction["location"]["longitude"],
    )

    if distance_km == 0:
        # Mismo punto: ninguna velocidad implícita es imposible.
        return None

    if elapsed_seconds <= 0:
        # Transacciones "simultáneas" (o fuera de orden) en ubicaciones
        # distintas: la velocidad implícita es infinita — se activa
        # directamente en vez de dividir por un intervalo <= 0.
        implied_speed_kmh = float("inf")
    else:
        implied_speed_kmh = distance_km / (elapsed_seconds / 3600)

    if implied_speed_kmh <= config.geo_max_speed_kmh:
        return None

    return RuleActivation(
        rule_id=RULE_GEO_IMPOSIBLE,
        points=config.geo_points,
        details={
            "distance_km": round(distance_km, 2),
            "elapsed_seconds": elapsed_seconds,
            "implied_speed_kmh": (
                None if implied_speed_kmh == float("inf") else round(implied_speed_kmh, 2)
            ),
            "max_plausible_speed_kmh": config.geo_max_speed_kmh,
            "previous_transaction_id": previous.get("transaction_id"),
        },
    )


def rule_comercio_riesgo(
    transaction: dict[str, Any], history: list[dict[str, Any]], config: ScoringConfig
) -> RuleActivation | None:
    merchant = transaction["merchant"]
    merchant_id = merchant["merchant_id"]
    category = merchant["category"]

    matched_by_id = merchant_id in config.risky_merchant_ids
    matched_by_category = category in config.risky_categories

    if not (matched_by_id or matched_by_category):
        return None

    return RuleActivation(
        rule_id=RULE_COMERCIO_RIESGO,
        points=config.risky_merchant_points,
        details={
            "merchant_id": merchant_id,
            "category": category,
            "matched_by_merchant_id": matched_by_id,
            "matched_by_category": matched_by_category,
        },
    )


_ALL_RULES = (rule_velocity, rule_monto_atipico, rule_geo_imposible, rule_comercio_riesgo)


def evaluate_all(
    transaction: dict[str, Any], history: list[dict[str, Any]], config: ScoringConfig
) -> ScoringResult:
    """
    Evalúa las cuatro reglas (sección 2.3, pasos 3-4: evaluar reglas, sumar
    puntos de las activadas) y devuelve el resultado agregado.
    """
    activations = []
    for rule in _ALL_RULES:
        activation = rule(transaction, history, config)
        if activation is not None:
            activations.append(activation)

    score = sum(activation.points for activation in activations)
    return ScoringResult(score=score, activations=activations)