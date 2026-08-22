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
def _build(backend_key: str) -> StorageBackend:
    backend_cls = _BACKENDS.get(backend_key)
    if not backend_cls:
        raise ValueError(f'Unknown storage backend: {backend_key}')
    return backend_cls()


def get_storage_backend() -> StorageBackend:
    return _build(settings.MEDIA_STORAGE_BACKEND)
