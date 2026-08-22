from unittest.mock import MagicMock, patch
from django.test import override_settings
from botocore.exceptions import ClientError
import pytest

from media_storage.backends.r2 import R2StorageBackend

R2_SETTINGS = {
    'BUCKET_NAME': 'test-bucket',
    'REGION': 'auto',
    'ENDPOINT': 'https://example.r2.cloudflarestorage.com',
    'ACCESS_KEY_ID': 'fake-key',
    'SECRET_ACCESS_KEY': 'fake-secret',
    'PUBLIC_DOMAIN': 'https://cdn.example.com',
}


@pytest.fixture
def mock_client():
    with patch('media_storage.backends.r2.boto3.client') as client_factory:
        client = MagicMock()
        client_factory.return_value = client
        yield client


@pytest.fixture
def backend(mock_client):
    with override_settings(CLOUDFLARE_R2=R2_SETTINGS):
        yield R2StorageBackend()


def test_put_calls_put_object_with_bucket_key_body_content_type(backend, mock_client):
    backend.put('products/1/photo.png', b'fake-bytes', 'image/png')
    mock_client.put_object.assert_called_once_with(
        Bucket='test-bucket', Key='products/1/photo.png',
        Body=b'fake-bytes', ContentType='image/png')


def test_delete_calls_delete_object(backend, mock_client):
    backend.delete('products/1/photo.png')
    mock_client.delete_object.assert_called_once_with(
        Bucket='test-bucket', Key='products/1/photo.png')


def test_exists_true_when_head_object_succeeds(backend, mock_client):
    mock_client.head_object.return_value = {}
    assert backend.exists('products/1/photo.png') is True


def test_exists_false_when_head_object_raises_client_error(backend, mock_client):
    mock_client.head_object.side_effect = ClientError(
        {'Error': {'Code': '404', 'Message': 'Not Found'}}, 'HeadObject')
    assert backend.exists('products/1/photo.png') is False


def test_public_url_joins_public_domain_and_key(backend):
    assert backend.public_url('products/1/photo.png') == (
        'https://cdn.example.com/products/1/photo.png')
