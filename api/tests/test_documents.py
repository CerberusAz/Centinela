import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import UserDelegationKey
from fastapi.testclient import TestClient

from app.core.config import Settings, StorageBackend, get_settings
from app.main import app
from app.storage.document_storage import (
    BlobDocumentStorage,
    DocumentSizeError,
    DocumentTypeError,
    _generate_blob_name,
)

# Cuenta inexistente: suficiente para las pruebas de este archivo porque la
# validación de tamaño y de tipo (magic bytes) ocurre en document_storage.py
# ANTES de cualquier llamada real a Azure (ver upload(): pasos 1 y 2). Construir
# BlobServiceClient/DefaultAzureCredential no abre conexión por sí solo — solo
# se conectaría al llamar upload_blob(), que estos casos nunca alcanzan.
_FAKE_ACCOUNT_URL = "https://fake-account.blob.core.windows.net"


def _run(coro):
    return asyncio.run(coro)


def _blob_settings(**overrides) -> Settings:
    values = {
        "storage_backend": StorageBackend.BLOB,
        "blob_account_url": _FAKE_ACCOUNT_URL,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: _blob_settings()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- Pruebas unitarias directas sobre BlobDocumentStorage (sin HTTP) ---


def test_oversized_file_is_rejected_before_any_azure_call():
    async def scenario():
        storage = BlobDocumentStorage(
            account_url=_FAKE_ACCOUNT_URL,
            container_name="identity-documents",
            max_size_bytes=10,
        )
        try:
            with pytest.raises(DocumentSizeError):
                await storage.upload(b"x" * 11, "documento.pdf")
        finally:
            await storage.close()

    _run(scenario())


def test_falsified_extension_is_rejected_by_content_not_by_name():
    async def scenario():
        storage = BlobDocumentStorage(
            account_url=_FAKE_ACCOUNT_URL,
            container_name="identity-documents",
            max_size_bytes=10_000,
        )
        try:
            # Nombre y content-type declarados como PDF, pero el contenido
            # real es texto plano: los magic bytes no coinciden con
            # %PDF/JPEG/PNG, así que debe rechazarse por contenido real,
            # no por la extensión que el usuario declaró (sección 2.10).
            with pytest.raises(DocumentTypeError):
                await storage.upload(b"esto no es un PDF real", "documento.pdf")
        finally:
            await storage.close()

    _run(scenario())


def _fake_delegation_key(start: datetime, expiry: datetime) -> UserDelegationKey:
    """
    Sustituto de prueba para azure.storage.blob.UserDelegationKey: no
    requiere red porque nunca sale de este proceso, pero tiene la misma
    forma que la respuesta real de `get_user_delegation_key` (obtenida vía
    Managed Identity), suficiente para ejercer la construcción del SAS.
    """
    key = UserDelegationKey()
    key.signed_oid = "11111111-1111-1111-1111-111111111111"
    key.signed_tid = "22222222-2222-2222-2222-222222222222"
    key.signed_start = start.isoformat()
    key.signed_expiry = expiry.isoformat()
    key.signed_service = "b"
    key.signed_version = "2024-11-04"
    key.value = "ZmFrZS1kZWxlZ2F0aW9uLWtleS12YWx1ZS1mb3ItdGVzdHM="
    return key


def test_generate_read_sas_url_returns_read_only_scoped_url():
    async def scenario():
        storage = BlobDocumentStorage(
            account_url=_FAKE_ACCOUNT_URL,
            container_name="identity-documents",
            max_size_bytes=10_000,
        )
        try:
            now = datetime.now(timezone.utc)
            fake_key = _fake_delegation_key(now, now + timedelta(minutes=30))
            blob_client = storage._client.get_blob_client(
                container="identity-documents", blob="caso-1/documento.pdf"
            )

            with patch.object(blob_client, "exists", new=AsyncMock(return_value=True)), patch.object(
                storage._client, "get_blob_client", return_value=blob_client
            ), patch.object(
                storage._client, "get_user_delegation_key", new=AsyncMock(return_value=fake_key)
            ):
                access = await storage.generate_read_sas_url(
                    "caso-1/documento.pdf", expiry_minutes=30
                )

            assert access["url"].startswith(_FAKE_ACCOUNT_URL)
            assert "identity-documents/caso-1/documento.pdf" in access["url"]
            assert "sp=r" in access["url"]  # permiso de solo lectura
            assert "sig=" in access["url"]  # firmado con el user delegation key
            assert "skoid=" in access["url"]  # evidencia de SAS delegado, no de cuenta
            assert access["expires_at"]
        finally:
            await storage.close()

    _run(scenario())


def test_generate_read_sas_url_raises_not_found_for_missing_blob():
    async def scenario():
        storage = BlobDocumentStorage(
            account_url=_FAKE_ACCOUNT_URL,
            container_name="identity-documents",
            max_size_bytes=10_000,
        )
        try:
            blob_client = storage._client.get_blob_client(
                container="identity-documents", blob="no-existe.pdf"
            )
            with patch.object(blob_client, "exists", new=AsyncMock(return_value=False)), patch.object(
                storage._client, "get_blob_client", return_value=blob_client
            ):
                with pytest.raises(ResourceNotFoundError):
                    await storage.generate_read_sas_url("no-existe.pdf")
        finally:
            await storage.close()

    _run(scenario())


def test_generated_blob_name_never_reuses_user_filename():
    blob_name = _generate_blob_name("pdf")

    assert blob_name != "documento.pdf"
    assert blob_name.endswith(".pdf")
    # Formato {uuid4}/{timestamp}.ext — dos segmentos separados por "/"
    assert len(blob_name.split("/")) == 2


# --- Pruebas de contrato HTTP sobre POST /documents ---


def test_upload_without_blob_backend_configured_returns_503():
    app.dependency_overrides[get_settings] = lambda: Settings(storage_backend=StorageBackend.MEMORY)
    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                "/documents",
                files={"file": ("documento.pdf", b"%PDF-1.4 contenido", "application/pdf")},
            )
        assert response.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_upload_oversized_file_via_endpoint_returns_400(client):
    app.dependency_overrides[get_settings] = lambda: _blob_settings(max_document_size_bytes=10)

    response = client.post(
        "/documents",
        files={"file": ("documento.pdf", b"x" * 100, "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "archivo_demasiado_grande"


def test_upload_falsified_extension_via_endpoint_returns_400(client):
    response = client.post(
        "/documents",
        files={"file": ("documento.pdf", b"contenido de texto plano, no es un PDF real", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "tipo_archivo_no_permitido"


# --- Pruebas de contrato HTTP sobre GET /documents/access-url ---


def test_access_url_without_blob_backend_configured_returns_503():
    app.dependency_overrides[get_settings] = lambda: Settings(storage_backend=StorageBackend.MEMORY)
    try:
        with TestClient(app) as test_client:
            response = test_client.get("/documents/access-url", params={"blob_name": "caso-1/documento.pdf"})
        assert response.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_access_url_returns_404_for_missing_document(client):
    with patch(
        "app.api.routes.BlobDocumentStorage.generate_read_sas_url",
        new=AsyncMock(side_effect=ResourceNotFoundError("no existe")),
    ):
        response = client.get("/documents/access-url", params={"blob_name": "no-existe.pdf"})

    assert response.status_code == 404
    assert response.json()["error"] == "documento_no_encontrado"


def test_access_url_returns_temporary_url_for_existing_document(client):
    fake_access = {
        "url": f"{_FAKE_ACCOUNT_URL}/identity-documents/caso-1/documento.pdf?sv=fake&sp=r&sig=fake",
        "expires_at": "2026-07-29T12:30:00+00:00",
    }
    with patch(
        "app.api.routes.BlobDocumentStorage.generate_read_sas_url",
        new=AsyncMock(return_value=fake_access),
    ):
        response = client.get("/documents/access-url", params={"blob_name": "caso-1/documento.pdf"})

    assert response.status_code == 200
    assert response.json() == fake_access