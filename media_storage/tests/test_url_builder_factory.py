from django.test import override_settings
import pytest

from media_storage.backends.url_builders.factory import _build, get_url_builder
from media_storage.backends.url_builders.local import LocalUrlBuilder
from media_storage.backends.url_builders.r2 import R2UrlBuilder

R2_SETTINGS = {
    'BUCKET_NAME': 'test-bucket', 'REGION': 'auto',
    'ENDPOINT': 'https://example.r2.cloudflarestorage.com',
    'ACCESS_KEY_ID': 'fake-key', 'SECRET_ACCESS_KEY': 'fake-secret',
    'PUBLIC_DOMAIN': 'https://cdn.example.com',
}


@pytest.fixture(autouse=True)
def clear_cache():
    _build.cache_clear()
    yield
    _build.cache_clear()


def test_returns_local_url_builder_by_default(tmp_path):
    with override_settings(MEDIA_STORAGE_BACKEND='local', MEDIA_ROOT=tmp_path):
        assert isinstance(get_url_builder(), LocalUrlBuilder)


def test_returns_r2_url_builder_when_configured():
    with override_settings(MEDIA_STORAGE_BACKEND='r2', CLOUDFLARE_R2=R2_SETTINGS):
        assert isinstance(get_url_builder(), R2UrlBuilder)


def test_unknown_backend_raises_value_error():
    with override_settings(MEDIA_STORAGE_BACKEND='ftp'):
        with pytest.raises(ValueError, match='Unknown storage backend'):
            get_url_builder()


def test_singleton_returns_same_instance(tmp_path):
    with override_settings(MEDIA_STORAGE_BACKEND='local', MEDIA_ROOT=tmp_path):
        assert get_url_builder() is get_url_builder()
