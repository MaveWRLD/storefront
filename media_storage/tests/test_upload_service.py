from io import BytesIO
from unittest.mock import MagicMock, patch
from PIL import Image as PILImage
import pytest

from media_storage.services.upload import InvalidImageError, delete_image, upload_image


def make_png_bytes():
    buf = BytesIO()
    PILImage.new('RGB', (10, 10)).save(buf, format='PNG')
    return buf.getvalue()


@pytest.fixture
def mock_backend():
    with patch('media_storage.services.upload.get_storage_backend') as factory:
        backend = MagicMock()
        factory.return_value = backend
        yield backend


def test_uploads_valid_png_and_returns_a_key_under_the_product(mock_backend):
    key = upload_image(BytesIO(make_png_bytes()), product_id=1)
    assert key.startswith('products/1/')
    assert key.endswith('.png')
    mock_backend.put.assert_called_once()
    called_key, called_data, called_content_type = mock_backend.put.call_args[0]
    assert called_key == key
    assert called_content_type == 'image/png'


def test_uploads_variant_tagged_image_under_variants_subpath(mock_backend):
    key = upload_image(BytesIO(make_png_bytes()), product_id=1, variant_id=9)
    assert key.startswith('products/1/variants/9/')


def test_rejects_file_over_10mb(mock_backend):
    oversized = BytesIO(b'\x00' * (10 * 1024 * 1024 + 1))
    with pytest.raises(InvalidImageError, match='exceeds 10MB'):
        upload_image(oversized, product_id=1)
    mock_backend.put.assert_not_called()


def test_rejects_disallowed_mime_type(mock_backend):
    with pytest.raises(InvalidImageError, match='Unsupported'):
        upload_image(BytesIO(b'plain text, not an image'), product_id=1)
    mock_backend.put.assert_not_called()


def test_delete_image_calls_backend_delete(mock_backend):
    delete_image('products/1/photo.png')
    mock_backend.delete.assert_called_once_with('products/1/photo.png')
