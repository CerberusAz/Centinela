from datetime import datetime, timedelta, timezone

import pytest

from rules import (
    RULE_COMERCIO_RIESGO,
    RULE_GEO_IMPOSIBLE,
    RULE_MONTO_ATIPICO,
    RULE_VELOCITY,
    ScoringConfig,
    evaluate_all,
    rule_comercio_riesgo,
    rule_geo_imposible,
    rule_monto_atipico,
    rule_velocity,
)

BOGOTA = {"latitude": 4.6097, "longitude": -74.0817}
MEDELLIN = {"latitude": 6.2442, "longitude": -75.5812}  # ~240 km de Bogotá
TOKYO = {"latitude": 35.6762, "longitude": 139.6503}  # ~14000 km de Bogotá

_BASE_TIME = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)


def _tx(**overrides):
    tx = {
        "transaction_id": "tx-current",
        "account_id": "acc-001",
        "amount_minor_units": 1500,
        "server_received_at": _BASE_TIME,
        "location": BOGOTA,
        "merchant": {"merchant_id": "merch-001", "category": "grocery"},
    }
    tx.update(overrides)
    return tx


def _history_item(minutes_ago: int, **overrides):
    item = _tx(
        transaction_id=f"tx-{minutes_ago}",
        server_received_at=_BASE_TIME - timedelta(minutes=minutes_ago),
    )
    item.update(overrides)
    return item


# --- Velocidad ---


def test_velocity_not_activated_below_threshold():
    config = ScoringConfig(velocity_max_count=5)
    history = [_history_item(m) for m in (1, 2, 3)]  # 3 previas + actual = 4 < 5

    assert rule_velocity(_tx(), history, config) is None


def test_velocity_activated_at_threshold_including_current():
    config = ScoringConfig(velocity_max_count=5, velocity_window_seconds=600)
    history = [_history_item(m) for m in (1, 2, 3, 4)]  # 4 previas + actual = 5

    activation = rule_velocity(_tx(), history, config)

    assert activation is not None
    assert activation.rule_id == RULE_VELOCITY
    assert activation.details["transaction_count"] == 5


def test_velocity_ignores_transactions_outside_window():
    config = ScoringConfig(velocity_max_count=3, velocity_window_seconds=300)
    # Dos dentro de la ventana de 5 min, dos muy anteriores (fuera de ventana).
    history = [
        _history_item(1),
        _history_item(2),
        _history_item(120),
        _history_item(240),
    ]

    activation = rule_velocity(_tx(), history, config)

    assert activation is not None
    assert activation.details["transaction_count"] == 3  # 2 en ventana + actual


# --- Monto atípico ---


def test_monto_atipico_not_activated_with_insufficient_history():
    config = ScoringConfig(amount_min_history_points=3)
    history = [_history_item(1, amount_minor_units=1000), _history_item(2, amount_minor_units=1000)]

    assert rule_monto_atipico(_tx(amount_minor_units=999_999), history, config) is None


def test_monto_atipico_not_activated_for_normal_amount():
    config = ScoringConfig(amount_min_history_points=3, amount_stddev_multiplier=3.0)
    history = [
        _history_item(1, amount_minor_units=1000),
        _history_item(2, amount_minor_units=1200),
        _history_item(3, amount_minor_units=900),
        _history_item(4, amount_minor_units=1100),
    ]

    assert rule_monto_atipico(_tx(amount_minor_units=1150), history, config) is None


def test_monto_atipico_activated_for_large_deviation():
    config = ScoringConfig(amount_min_history_points=3, amount_stddev_multiplier=3.0)
    history = [
        _history_item(1, amount_minor_units=1000),
        _history_item(2, amount_minor_units=1050),
        _history_item(3, amount_minor_units=950),
        _history_item(4, amount_minor_units=1020),
    ]

    activation = rule_monto_atipico(_tx(amount_minor_units=500_000), history, config)

    assert activation is not None
    assert activation.rule_id == RULE_MONTO_ATIPICO
    assert activation.details["observed_amount_minor_units"] == 500_000
    assert activation.details["history_size"] == 4


def test_monto_atipico_handles_zero_stddev_history():
    config = ScoringConfig(amount_min_history_points=3)
    history = [_history_item(m, amount_minor_units=1000) for m in (1, 2, 3)]

    assert rule_monto_atipico(_tx(amount_minor_units=1000), history, config) is None
    activation = rule_monto_atipico(_tx(amount_minor_units=1001), history, config)
    assert activation is not None


# --- Geo-imposible ---


def test_geo_imposible_not_activated_without_history():
    config = ScoringConfig()
    assert rule_geo_imposible(_tx(), [], config) is None


def test_geo_imposible_not_activated_for_plausible_travel():
    config = ScoringConfig(geo_max_speed_kmh=900.0)
    # Bogotá -> Medellín (~240 km) en 2 horas: ~120 km/h, plausible por tierra/aire.
    history = [
        _history_item(120, location=MEDELLIN),
    ]

    assert rule_geo_imposible(_tx(location=BOGOTA), history, config) is None


def test_geo_imposible_activated_for_impossible_travel():
    config = ScoringConfig(geo_max_speed_kmh=900.0)
    # Bogotá -> Tokio (~14000 km) en 10 minutos: velocidad implícita absurda.
    history = [
        _history_item(10, location=TOKYO),
    ]

    activation = rule_geo_imposible(_tx(location=BOGOTA), history, config)

    assert activation is not None
    assert activation.rule_id == RULE_GEO_IMPOSIBLE
    assert activation.details["implied_speed_kmh"] > 900.0
    assert activation.details["previous_transaction_id"] == "tx-10"


def test_geo_imposible_not_activated_for_same_location():
    config = ScoringConfig()
    history = [_history_item(0, location=BOGOTA)]

    assert rule_geo_imposible(_tx(location=BOGOTA), history, config) is None


def test_geo_imposible_handles_simultaneous_transactions_without_division_by_zero():
    config = ScoringConfig()
    # Misma marca de tiempo que la actual, pero en Tokio: tiempo transcurrido <= 0.
    simultaneous = _tx(transaction_id="tx-sim", location=TOKYO, server_received_at=_BASE_TIME)

    activation = rule_geo_imposible(_tx(location=BOGOTA), [simultaneous], config)

    assert activation is not None
    assert activation.details["implied_speed_kmh"] is None  # infinito, no serializable
    assert activation.details["elapsed_seconds"] <= 0


def test_geo_imposible_uses_most_recent_prior_transaction():
    config = ScoringConfig(geo_max_speed_kmh=900.0)
    history = [
        _history_item(120, location=TOKYO),  # más antigua: si se usara, sería imposible
        _history_item(60, location=MEDELLIN),  # más reciente: 246 km en 1h ~ plausible
    ]

    assert rule_geo_imposible(_tx(location=BOGOTA), history, config) is None


# --- Comercio de riesgo ---


def test_comercio_riesgo_not_activated_for_normal_merchant():
    config = ScoringConfig()
    tx = _tx(merchant={"merchant_id": "merch-001", "category": "grocery"})

    assert rule_comercio_riesgo(tx, [], config) is None


def test_comercio_riesgo_activated_by_category():
    config = ScoringConfig(risky_categories=frozenset({"gambling"}))
    tx = _tx(merchant={"merchant_id": "merch-999", "category": "gambling"})

    activation = rule_comercio_riesgo(tx, [], config)

    assert activation is not None
    assert activation.rule_id == RULE_COMERCIO_RIESGO
    assert activation.details["matched_by_category"] is True
    assert activation.details["matched_by_merchant_id"] is False


def test_comercio_riesgo_activated_by_merchant_id():
    config = ScoringConfig(risky_categories=frozenset(), risky_merchant_ids=frozenset({"merch-666"}))
    tx = _tx(merchant={"merchant_id": "merch-666", "category": "grocery"})

    activation = rule_comercio_riesgo(tx, [], config)

    assert activation is not None
    assert activation.details["matched_by_merchant_id"] is True


# --- evaluate_all ---


def test_evaluate_all_sums_points_of_activated_rules_only():
    config = ScoringConfig(
        velocity_max_count=2,
        velocity_points=10,
        risky_categories=frozenset({"gambling"}),
        risky_merchant_points=20,
        amount_min_history_points=999,  # nunca se activa: fuerza historial insuficiente
        geo_max_speed_kmh=999_999,  # nunca se activa
    )
    history = [_history_item(1)]  # dispara velocidad (2 con la actual)
    tx = _tx(merchant={"merchant_id": "m", "category": "gambling"})

    result = evaluate_all(tx, history, config)

    assert result.score == 30  # 10 (velocidad) + 20 (comercio de riesgo)
    assert set(result.rule_ids) == {RULE_VELOCITY, RULE_COMERCIO_RIESGO}


def test_evaluate_all_no_activations_yields_zero_score():
    config = ScoringConfig(velocity_max_count=999, amount_min_history_points=999, geo_max_speed_kmh=999_999)

    result = evaluate_all(_tx(), [], config)

    assert result.score == 0
    assert result.activations == []


def test_threshold_changes_whether_case_opens_without_changing_rule_logic():
    config_low = ScoringConfig(
        velocity_max_count=2, velocity_points=50, score_threshold=40,
        amount_min_history_points=999, geo_max_speed_kmh=999_999,
    )
    config_high = ScoringConfig(
        velocity_max_count=2, velocity_points=50, score_threshold=1000,
        amount_min_history_points=999, geo_max_speed_kmh=999_999,
    )
    history = [_history_item(1)]

    result_low = evaluate_all(_tx(), history, config_low)
    result_high = evaluate_all(_tx(), history, config_high)

    # Mismo score (la lógica de reglas no cambia), pero el umbral decide
    # si se abriría caso o no — exactamente el comportamiento que exige
    # el entregable 6 ("modificable sin redespliegue").
    assert result_low.score == result_high.score == 50
    assert result_low.exceeds_threshold(config_low) is True
    assert result_high.exceeds_threshold(config_high) is False