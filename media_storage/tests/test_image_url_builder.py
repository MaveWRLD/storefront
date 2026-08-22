from unittest.mock import MagicMock, patch

from media_storage.services.image_url_builder import build_srcset, build_url


def test_build_url_delegates_to_url_builder():
    with patch('media_storage.services.image_url_builder.get_url_builder') as factory:
        builder = MagicMock()
        builder.build.return_value = 'https://cdn.example.com/products/1/photo.png'
        factory.return_value = builder

        assert build_url('products/1/photo.png') == (
            'https://cdn.example.com/products/1/photo.png')
        builder.build.assert_called_once_with(
            'products/1/photo.png', width=None, quality=None, format=None)


def test_build_url_forwards_transform_kwargs():
    with patch('media_storage.services.image_url_builder.get_url_builder') as factory:
        builder = MagicMock()
        builder.build.return_value = 'https://cdn.example.com/x.png'
        factory.return_value = builder

        build_url('products/1/photo.png', width=400, quality=60, format='webp')
        builder.build.assert_called_once_with(
            'products/1/photo.png', width=400, quality=60, format='webp')


def test_build_url_returns_empty_string_for_falsy_key():
    with patch('media_storage.services.image_url_builder.get_url_builder') as factory:
        assert build_url('') == ''
        factory.assert_not_called()


def test_build_srcset_returns_width_descriptor_pairs_in_order():
    with patch('media_storage.services.image_url_builder.get_url_builder') as factory:
        builder = MagicMock()
        builder.build.side_effect = lambda key, width, quality, format: f'https://cdn.example.com/{key}?w={width}'
        factory.return_value = builder

        result = build_srcset('products/1/photo.png')

        assert result == (
            'https://cdn.example.com/products/1/photo.png?w=400 400w, '
            'https://cdn.example.com/products/1/photo.png?w=800 800w, '
            'https://cdn.example.com/products/1/photo.png?w=1200 1200w, '
            'https://cdn.example.com/products/1/photo.png?w=1600 1600w')


def test_build_srcset_honors_custom_widths():
    with patch('media_storage.services.image_url_builder.get_url_builder') as factory:
        builder = MagicMock()
        builder.build.side_effect = lambda key, width, quality, format: f'https://cdn.example.com/{key}?w={width}'
        factory.return_value = builder

        result = build_srcset('products/1/photo.png', widths=(200, 400))

        assert result == (
            'https://cdn.example.com/products/1/photo.png?w=200 200w, '
            'https://cdn.example.com/products/1/photo.png?w=400 400w')


def test_build_srcset_returns_empty_string_for_falsy_key():
    with patch('media_storage.services.image_url_builder.get_url_builder') as factory:
        assert build_srcset('') == ''
        factory.assert_not_called()
