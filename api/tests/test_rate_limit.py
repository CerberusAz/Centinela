import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limiter import InMemoryRateLimiter, RateLimitConfig, get_rate_limiter
from app.main import app
from app.messaging.publisher import NoOpEventPublisher, get_event_publisher
from app.storage.factory import get_transaction_storage
from app.storage.memory_storage import InMemoryTransactionStorage


class FakeClock:
    """Reloj inyectable y avanzable a voluntad -- evita depender de time.sleep() real en los tests."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _valid_payload(**overrides):
    payload = {
        "transaction_id": str(uuid.uuid4()),
        "account_id": "acc-001",
        "amount_minor_units": 1500,
        "currency": "USD",
        "client_timestamp": datetime.now(timezone.utc).isoformat(),
        "location": {"latitude": 4.6097, "longitude": -74.0817},
        "merchant": {"merchant_id": "merch-001", "category": "grocery"},
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def limited_client():
    clock = FakeClock()
    limiter = InMemoryRateLimiter(RateLimitConfig(window_seconds=60, max_requests=3), clock=clock)

    app.dependency_overrides[get_transaction_storage] = lambda: InMemoryTransactionStorage()
    app.dependency_overrides[get_event_publisher] = lambda: NoOpEventPublisher()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter

    with TestClient(app) as test_client:
        yield test_client, clock

    app.dependency_overrides.clear()


def test_requests_under_the_limit_all_succeed(limited_client):
    test_client, _ = limited_client

    for _ in range(3):
        response = test_client.post("/transactions", json=_valid_payload())
        assert response.status_code == 201


def test_request_over_the_limit_is_rejected_with_429(limited_client):
    test_client, _ = limited_client
    for _ in range(3):
        test_client.post("/transactions", json=_valid_payload())

    response = test_client.post("/transactions", json=_valid_payload())

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0


def test_rate_limit_response_does_not_leak_internal_details(limited_client):
    test_client, _ = limited_client
    for _ in range(3):
        test_client.post("/transactions", json=_valid_payload())

    response = test_client.post("/transactions", json=_valid_payload())
    body_text = response.text.lower()

    assert "traceback" not in body_text
    assert "site-packages" not in body_text
    assert ".py" not in body_text


def test_limit_resets_after_the_window_elapses(limited_client):
    test_client, clock = limited_client
    for _ in range(3):
        test_client.post("/transactions", json=_valid_payload())
    blocked = test_client.post("/transactions", json=_valid_payload())
    assert blocked.status_code == 429

    clock.advance(61)  # supera la ventana de 60s configurada

    response = test_client.post("/transactions", json=_valid_payload())
    assert response.status_code == 201


def test_different_origins_are_tracked_independently(limited_client):
    test_client, _ = limited_client
    for _ in range(3):
        test_client.post(
            "/transactions", json=_valid_payload(), headers={"X-Forwarded-For": "10.0.0.1"}
        )
    exhausted = test_client.post(
        "/transactions", json=_valid_payload(), headers={"X-Forwarded-For": "10.0.0.1"}
    )
    assert exhausted.status_code == 429

    # Un origen distinto no debe verse afectado por el consumo del primero.
    response = test_client.post(
        "/transactions", json=_valid_payload(), headers={"X-Forwarded-For": "10.0.0.2"}
    )
    assert response.status_code == 201


def test_get_transaction_endpoint_is_not_rate_limited(limited_client):
    """
    La limitación de tasa se acota a POST /transactions (el endpoint que
    dispara costo real: persistencia + evento + motor de scoring, sección
    2.7). GET /transactions/{id} no dispara ningún costo comparable.
    """
    test_client, _ = limited_client
    for _ in range(3):
        test_client.post("/transactions", json=_valid_payload())
    assert test_client.post("/transactions", json=_valid_payload()).status_code == 429

    response = test_client.get(f"/transactions/{uuid.uuid4()}")
    assert response.status_code == 404  # no encontrada, pero NO 429
