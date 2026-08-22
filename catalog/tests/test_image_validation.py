import json
from io import BytesIO

from django.contrib.auth import get_user_model
from PIL import Image as PILImage
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Product
from djmoney.money import Money

User = get_user_model()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


@pytest.fixture
def product(db):
    return Product.objects.create(
        title='Shirt', slug='shirt', price=Money(25, 'GHS'))


def oversized_png(name='big.png'):
    """A structurally-valid PNG (so DRF's ImageField itself accepts it)
    padded with trailing bytes past the 10MB limit our own validation
    enforces."""
    buf = BytesIO()
    PILImage.new('RGB', (10, 10)).save(buf, format='PNG')
    data = buf.getvalue()
    padded = data + b'\x00' * (10 * 1024 * 1024 + 1 - len(data))
    oversized = BytesIO(padded)
    oversized.name = name
    return oversized


def gif_image(name='test.gif'):
    """Valid-per-PIL image in a format our MIME allowlist rejects."""
    buf = BytesIO()
    PILImage.new('RGB', (10, 10)).save(buf, format='GIF')
    buf.seek(0)
    buf.name = name
    return buf


@pytest.mark.django_db
class TestImageValidationReturns400NotServerError:
    def test_oversized_image_on_product_create_returns_400(self, admin_client):
        data = {
            'name': 'A Product',
            'price': {'amount': 25, 'currency': 'GHS'},
            'axes': [{'name': 'Size', 'sortOrder': 0,
                      'allowedValues': [{'name': 'Small', 'code': 'S'}]}],
        }
        response = admin_client.post(
            '/store-admin/products/',
            {'data': json.dumps(data), 'images': [oversized_png()]},
            format='multipart')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        message = json.dumps(response.data).lower()
        assert 'size' in message or '10mb' in message

    def test_disallowed_format_on_product_create_returns_400(self, admin_client):
        data = {
            'name': 'A Product',
            'price': {'amount': 25, 'currency': 'GHS'},
            'axes': [{'name': 'Size', 'sortOrder': 0,
                      'allowedValues': [{'name': 'Small', 'code': 'S'}]}],
        }
        response = admin_client.post(
            '/store-admin/products/',
            {'data': json.dumps(data), 'images': [gif_image()]},
            format='multipart')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'gif' in json.dumps(response.data).lower()

    def test_oversized_image_on_add_image_endpoint_returns_400(self, admin_client, product):
        response = admin_client.post(
            f'/store-admin/products/{product.id}/images/',
            {'image': oversized_png()}, format='multipart')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_disallowed_format_on_add_image_endpoint_returns_400(self, admin_client, product):
        response = admin_client.post(
            f'/store-admin/products/{product.id}/images/',
            {'image': gif_image()}, format='multipart')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'gif' in json.dumps(response.data).lower()
