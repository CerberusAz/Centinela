from fastapi import Depends

from app.core.config import Settings, StorageBackend, get_settings
from app.storage.blob_storage import BlobTransactionStorage
from app.storage.cosmos_storage import CosmosTransactionStorage
from app.storage.dual_storage import DualTransactionStorage
from app.storage.memory_storage import InMemoryTransactionStorage
from app.storage.ports import TransactionStorage

_storage_instance: TransactionStorage | None = None


def _require(value: str | None, env_var: str, backend: str) -> str:
    if not value:
        raise RuntimeError(f"{env_var} es obligatorio cuando CENTINELA_STORAGE_BACKEND={backend}")
    return value


def get_transaction_storage(settings: Settings = Depends(get_settings)) -> TransactionStorage:
    """
    Único punto de decisión sobre qué backend de persistencia usar, elegido
    por configuración (CENTINELA_STORAGE_BACKEND). Cambiar de memoria a Blob
    Storage (o a la persistencia dual de semana 2) no requiere tocar la
    capa de servicio ni el endpoint.
    """
    global _storage_instance
    if _storage_instance is None:
        if settings.storage_backend == StorageBackend.BLOB:
            blob_url = _require(settings.blob_account_url, "CENTINELA_BLOB_ACCOUNT_URL", "blob")
            _storage_instance = BlobTransactionStorage(
                account_url=blob_url,
                container_name=settings.blob_container_raw_transactions,
            )
        elif settings.storage_backend == StorageBackend.DUAL:
            blob_url = _require(settings.blob_account_url, "CENTINELA_BLOB_ACCOUNT_URL", "dual")
            cosmos_url = _require(settings.cosmos_account_url, "CENTINELA_COSMOS_ACCOUNT_URL", "dual")
            _storage_instance = DualTransactionStorage(
                primary=BlobTransactionStorage(
                    account_url=blob_url,
                    container_name=settings.blob_container_raw_transactions,
                ),
                secondary=CosmosTransactionStorage(
                    account_url=cosmos_url,
                    database_name=settings.cosmos_database_name,
                    container_name=settings.cosmos_container_transactions,
                ),
            )
        else:
            _storage_instance = InMemoryTransactionStorage()
    return _storage_instance
