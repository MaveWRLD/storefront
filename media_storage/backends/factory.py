from functools import lru_cache
from django.conf import settings
from .base import StorageBackend
from .local import LocalStorageBackend
from .r2 import R2StorageBackend

_BACKENDS = {
    'local': LocalStorageBackend,
    'r2': R2StorageBackend,
}


@lru_cache
def get_storage_backend() -> StorageBackend:
    backend_key = settings.MEDIA_STORAGE_BACKEND
    backend_cls = _BACKENDS.get(backend_key)
    if not backend_cls:
        raise ValueError(f'Unknown storage backend: {backend_key}')
    return backend_cls()
