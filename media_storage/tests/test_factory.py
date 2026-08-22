from django.test import override_settings
import pytest

from media_storage.backends.factory import get_storage_backend
from media_storage.backends.local import LocalStorageBackend
from media_storage.backends.r2 import R2StorageBackend

R2_SETTINGS = {
    'BUCKET_NAME': 'test-bucket', 'REGION': 'auto',
    'ENDPOINT': 'https://example.r2.cloudflarestorage.com',
    'ACCESS_KEY_ID': 'fake-key', 'SECRET_ACCESS_KEY': 'fake-secret',
    'PUBLIC_DOMAIN': 'https://cdn.example.com',
}


@pytest.fixture(autouse=True)
def clear_cache():
    get_storage_backend.cache_clear()
    yield
    get_storage_backend.cache_clear()


def test_returns_local_backend_by_default(tmp_path):
    with override_settings(MEDIA_STORAGE_BACKEND='local', MEDIA_ROOT=tmp_path):
        assert isinstance(get_storage_backend(), LocalStorageBackend)


def test_returns_r2_backend_when_configured():
    with override_settings(MEDIA_STORAGE_BACKEND='r2', CLOUDFLARE_R2=R2_SETTINGS):
        assert isinstance(get_storage_backend(), R2StorageBackend)


def test_unknown_backend_raises_value_error():
    with override_settings(MEDIA_STORAGE_BACKEND='ftp'):
        with pytest.raises(ValueError, match='Unknown storage backend'):
            get_storage_backend()


def test_singleton_returns_same_instance(tmp_path):
    with override_settings(MEDIA_STORAGE_BACKEND='local', MEDIA_ROOT=tmp_path):
        assert get_storage_backend() is get_storage_backend()
