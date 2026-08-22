from django.test import override_settings
import pytest

from media_storage.backends.local import LocalStorageBackend


@pytest.fixture
def backend(tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path, MEDIA_URL='/media/'):
        yield LocalStorageBackend()


def test_put_then_exists(backend):
    backend.put('products/1/photo.png', b'fake-bytes', 'image/png')
    assert backend.exists('products/1/photo.png') is True


def test_exists_false_for_missing_key(backend):
    assert backend.exists('products/1/missing.png') is False


def test_put_then_delete_removes_it(backend):
    backend.put('products/1/photo.png', b'fake-bytes', 'image/png')
    backend.delete('products/1/photo.png')
    assert backend.exists('products/1/photo.png') is False


def test_delete_missing_key_is_a_noop(backend):
    backend.delete('products/1/missing.png')  # must not raise


def test_put_creates_intermediate_directories(backend):
    backend.put('products/1/variants/9/photo.png', b'fake-bytes', 'image/png')
    assert backend.exists('products/1/variants/9/photo.png') is True


def test_public_url_joins_media_url_and_key(backend):
    assert backend.public_url('products/1/photo.png') == '/media/products/1/photo.png'
