from pathlib import Path
from django.conf import settings
from .base import StorageBackend


class LocalStorageBackend(StorageBackend):
    """Dev/test backend — files live under settings.MEDIA_ROOT, served at
    settings.MEDIA_URL. Mirrors the app's pre-abstraction behavior."""

    def __init__(self):
        self._root = Path(settings.MEDIA_ROOT)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._root / key

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def public_url(self, key: str) -> str:
        return f"{settings.MEDIA_URL.rstrip('/')}/{key}"
