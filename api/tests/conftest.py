import pytest
from fastapi.testclient import TestClient

from app.core.rate_limiter import InMemoryRateLimiter, RateLimitConfig, get_rate_limiter
from app.main import app
from app.messaging.publisher import NoOpEventPublisher, get_event_publisher
from app.storage.factory import get_transaction_storage
from app.storage.memory_storage import InMemoryTransactionStorage


@pytest.fixture
def client():
    """
    Cada test recibe un storage en memoria nuevo (vía dependency_overrides),
    para no depender de Azure ni compartir estado entre pruebas. El límite
    de tasa se sobreescribe con uno muy generoso: la limitación de tasa en
    sí se prueba por separado en test_rate_limit.py, con su propio
    limitador y su propio reloj controlado — no debe interferir con el
    resto de la suite.
    """
    storage = InMemoryTransactionStorage()
    app.dependency_overrides[get_transaction_storage] = lambda: storage
    app.dependency_overrides[get_event_publisher] = lambda: NoOpEventPublisher()
    app.dependency_overrides[get_rate_limiter] = lambda: InMemoryRateLimiter(
        RateLimitConfig(window_seconds=60, max_requests=10_000)
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
