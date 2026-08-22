from functools import lru_cache
from django.conf import settings
from .base import UrlBuilder
from .local import LocalUrlBuilder
from .r2 import R2UrlBuilder

_BUILDERS = {
    'local': LocalUrlBuilder,
    'r2': R2UrlBuilder,
}


@lru_cache
def _build(backend_key: str) -> UrlBuilder:
    builder_cls = _BUILDERS.get(backend_key)
    if not builder_cls:
        raise ValueError(f'Unknown storage backend: {backend_key}')
    return builder_cls()


def get_url_builder() -> UrlBuilder:
    return _build(settings.MEDIA_STORAGE_BACKEND)
