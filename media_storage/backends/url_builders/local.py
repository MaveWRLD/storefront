from media_storage.backends.factory import get_storage_backend
from .base import UrlBuilder


class LocalUrlBuilder(UrlBuilder):
    """Dev backend — no resize proxy in front of local media, so transform
    kwargs are accepted (for interface symmetry with R2UrlBuilder) but
    ignored. Delegates to LocalStorageBackend.public_url for the actual
    MEDIA_URL/key join, rather than duplicating that logic here."""

    def build(self, key: str, *, width: int | None = None,
              quality: int | None = None, format: str | None = None) -> str:
        return get_storage_backend().public_url(key)
