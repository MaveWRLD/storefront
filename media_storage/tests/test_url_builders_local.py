from django.test import override_settings
import pytest

from media_storage.backends.factory import _build as _backend_build
from media_storage.backends.url_builders.local import LocalUrlBuilder


@pytest.fixture(autouse=True)
def clear_backend_cache():
    _backend_build.cache_clear()
    yield
    _backend_build.cache_clear()


@pytest.fixture
def builder(tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path, MEDIA_URL='/media/',
                            MEDIA_STORAGE_BACKEND='local'):
        yield LocalUrlBuilder()


def test_build_matches_local_backend_public_url(builder):
    assert builder.build('products/1/photo.png') == '/media/products/1/photo.png'


def test_build_ignores_transform_kwargs(builder):
    assert builder.build('products/1/photo.png', width=400, quality=60,
                          format='webp') == '/media/products/1/photo.png'
