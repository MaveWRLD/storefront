from django.test import override_settings
import pytest

from media_storage.backends.url_builders.r2 import R2UrlBuilder

R2_SETTINGS = {
    'BUCKET_NAME': 'test-bucket', 'REGION': 'auto',
    'ENDPOINT': 'https://example.r2.cloudflarestorage.com',
    'ACCESS_KEY_ID': 'fake-key', 'SECRET_ACCESS_KEY': 'fake-secret',
    'PUBLIC_DOMAIN': 'https://cdn.example.com',
}


@pytest.fixture
def builder():
    with override_settings(CLOUDFLARE_R2=R2_SETTINGS):
        yield R2UrlBuilder()


def test_build_applies_default_transform_params(builder):
    assert builder.build('products/1/photo.png') == (
        'https://cdn.example.com/cdn-cgi/image/'
        'width=1200,quality=80,format=auto/products/1/photo.png')


def test_build_honors_explicit_transform_kwargs(builder):
    assert builder.build('products/1/photo.png', width=400, quality=60,
                          format='webp') == (
        'https://cdn.example.com/cdn-cgi/image/'
        'width=400,quality=60,format=webp/products/1/photo.png')


def test_build_reads_domain_from_settings():
    with override_settings(CLOUDFLARE_R2={**R2_SETTINGS,
                                           'PUBLIC_DOMAIN': 'https://other.example.com/'}):
        builder = R2UrlBuilder()
        assert builder.build('products/1/photo.png').startswith(
            'https://other.example.com/cdn-cgi/image/')
