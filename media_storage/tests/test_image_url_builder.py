from unittest.mock import MagicMock, patch

from media_storage.services.image_url_builder import build_url


def test_build_url_delegates_to_backend_public_url():
    with patch('media_storage.services.image_url_builder.get_storage_backend') as factory:
        backend = MagicMock()
        backend.public_url.return_value = 'https://cdn.example.com/products/1/photo.png'
        factory.return_value = backend

        assert build_url('products/1/photo.png') == (
            'https://cdn.example.com/products/1/photo.png')
        backend.public_url.assert_called_once_with('products/1/photo.png')
