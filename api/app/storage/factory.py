from fastapi import Depends

from app.core.config import Settings, StorageBackend, get_settings
from app.storage.blob_storage import BlobTransactionStorage
from app.storage.memory_storage import InMemoryTransactionStorage
from app.storage.ports import TransactionStorage

_storage_instance: TransactionStorage | None = None


def get_transaction_storage(settings: Settings = Depends(get_settings)) -> TransactionStorage:
    """
    Único punto de decisión sobre qué backend de persistencia usar, elegido
    por configuración (CENTINELA_STORAGE_BACKEND). Cambiar de memoria a Blob
    Storage no requiere tocar la capa de servicio ni el endpoint.
    """
    global _storage_instance
    if _storage_instance is None:
        if settings.storage_backend == StorageBackend.BLOB:
            if not settings.blob_account_url:
                raise RuntimeError(
                    "CENTINELA_BLOB_ACCOUNT_URL es obligatorio cuando "
                    "CENTINELA_STORAGE_BACKEND=blob"
                )
            _storage_instance = BlobTransactionStorage(
                account_url=settings.blob_account_url,
                container_name=settings.blob_container_raw_transactions,
            )
        else:
            _storage_instance = InMemoryTransactionStorage()
    return _storage_instance
