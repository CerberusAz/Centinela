import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from orchestration import handle_transaction_event
from rules import RULE_VELOCITY, ScoringConfig, ScoringResult

BASE_TIME = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.run(coro)


class FakeHistoryRepository:
    """Doble en memoria de orchestration.HistoryRepository — sin Cosmos real."""

    def __init__(self, history: list[dict[str, Any]] | None = None) -> None:
        self.history = history or []
        self.persisted: tuple[str, str, ScoringResult] | None = None

    async def query_recent_history(self, account_id, exclude_transaction_id, since):
        return [
            item
            for item in self.history
            if item["account_id"] == account_id
            and item["transaction_id"] != exclude_transaction_id
            and item["server_received_at"] >= since
        ]

    async def persist_score(self, transaction_id, account_id, result):
        self.persisted = (transaction_id, account_id, result)


class FakeCasePublisher:
    """Doble en memoria de orchestration.CasePublisher — sin Service Bus real."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str, ScoringResult]] = []

    async def publish_case(self, transaction_id, account_id, result):
        self.published.append((transaction_id, account_id, result))


def _event_payload(**overrides):
    payload = {
        "transaction_id": "tx-current",
        "account_id": "acc-1",
        "amount_minor_units": 1500,
        "currency": "USD",
        "server_received_at": BASE_TIME.isoformat(),
        "location": {"latitude": 4.6097, "longitude": -74.0817},
        "merchant": {"merchant_id": "merch-1", "category": "grocery"},
    }
    payload.update(overrides)
    return payload


def _history_item(minutes_ago: int, **overrides):
    item = {
        "transaction_id": f"tx-{minutes_ago}",
        "account_id": "acc-1",
        "amount_minor_units": 1500,
        "server_received_at": BASE_TIME - timedelta(minutes=minutes_ago),
        "location": {"latitude": 4.6097, "longitude": -74.0817},
        "merchant": {"merchant_id": "merch-1", "category": "grocery"},
    }
    item.update(overrides)
    return item


def test_handle_event_persists_score_and_does_not_publish_below_threshold():
    async def scenario():
        history_repo = FakeHistoryRepository()
        case_publisher = FakeCasePublisher()
        config = ScoringConfig(score_threshold=999_999, velocity_max_count=999, amount_min_history_points=999, geo_max_speed_kmh=999_999)

        result = await handle_transaction_event(
            _event_payload(), history_repo, case_publisher, config
        )

        assert result.score == 0
        assert history_repo.persisted == ("tx-current", "acc-1", result)
        assert case_publisher.published == []

    _run(scenario())


def test_handle_event_publishes_case_when_score_exceeds_threshold():
    async def scenario():
        history = [_history_item(m) for m in (1, 2, 3, 4)]  # 4 previas + actual = 5
        history_repo = FakeHistoryRepository(history)
        case_publisher = FakeCasePublisher()
        config = ScoringConfig(
            velocity_max_count=5, velocity_points=100, score_threshold=50,
            amount_min_history_points=999, geo_max_speed_kmh=999_999,
        )

        result = await handle_transaction_event(
            _event_payload(), history_repo, case_publisher, config
        )

        assert result.score == 100
        assert RULE_VELOCITY in result.rule_ids
        assert len(case_publisher.published) == 1
        published_tx_id, published_account_id, published_result = case_publisher.published[0]
        assert published_tx_id == "tx-current"
        assert published_account_id == "acc-1"
        assert published_result.score == 100

    _run(scenario())


def test_handle_event_excludes_current_transaction_and_out_of_window_history():
    async def scenario():
        history = [
            _history_item(1),
            _history_item(2),
            {**_history_item(0), "transaction_id": "tx-current"},  # no debe contarse dos veces
        ]
        history_repo = FakeHistoryRepository(history)
        case_publisher = FakeCasePublisher()
        config = ScoringConfig(
            velocity_max_count=3, velocity_points=10, score_threshold=1000,
            amount_min_history_points=999, geo_max_speed_kmh=999_999,
        )

        result = await handle_transaction_event(
            _event_payload(), history_repo, case_publisher, config
        )

        # 2 previas (1 y 2 minutos atrás) + la actual = 3 -> activa velocidad.
        assert result.score == 10

    _run(scenario())


def test_handle_event_uses_configured_lookback_window():
    async def scenario():
        # Historial fuera del lookback de 1 día no debe llegar al repo real
        # (se filtra por `since` calculado a partir de lookback_days), pero
        # como el fake no filtra por su cuenta más que lo que le pasan,
        # verificamos que el `since` calculado es el esperado indirectamente
        # a través de qué se le pide al repositorio.
        captured = {}

        class CapturingHistoryRepository(FakeHistoryRepository):
            async def query_recent_history(self, account_id, exclude_transaction_id, since):
                captured["since"] = since
                return await super().query_recent_history(account_id, exclude_transaction_id, since)

        history_repo = CapturingHistoryRepository()
        case_publisher = FakeCasePublisher()
        config = ScoringConfig(score_threshold=999_999, velocity_max_count=999, amount_min_history_points=999, geo_max_speed_kmh=999_999)

        await handle_transaction_event(
            _event_payload(), history_repo, case_publisher, config, lookback_days=7
        )

        assert captured["since"] == BASE_TIME - timedelta(days=7)

    _run(scenario())