import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.messaging.publisher import NoOpEventPublisher, get_event_publisher
from app.storage.factory import get_transaction_storage
from app.storage.memory_storage import InMemoryTransactionStorage


@pytest.fixture
def client():
    """
    Cada test recibe un storage en memoria nuevo (vía dependency_overrides),
    para no depender de Azure ni compartir estado entre pruebas.
    """
    storage = InMemoryTransactionStorage()
    app.dependency_overrides[get_transaction_storage] = lambda: storage
    app.dependency_overrides[get_event_publisher] = lambda: NoOpEventPublisher()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
