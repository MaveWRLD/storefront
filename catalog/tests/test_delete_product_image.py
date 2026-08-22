from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from PIL import Image as PILImage
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Product, ProductImage
from djmoney.money import Money

User = get_user_model()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


def make_image(name='test.png'):
    buf = BytesIO()
    PILImage.new('RGB', (10, 10)).save(buf, format='PNG')
    buf.seek(0)
    buf.name = name
    return buf


@pytest.fixture
def product(db):
    return Product.objects.create(
        title='Shirt', slug='shirt', price=Money(25, 'GHS'))


@pytest.mark.django_db
def test_deleting_a_product_image_calls_delete_image(admin_client, product):
    with patch('catalog.serializers.upload_image', return_value='products/1/x.png'):
        create_resp = admin_client.post(
            f'/store-admin/products/{product.id}/images/',
            {'image': make_image()}, format='multipart')
    assert create_resp.status_code == status.HTTP_201_CREATED
    image_id = create_resp.data['id']

    with patch('catalog.views.delete_image') as mock_delete_image:
        delete_resp = admin_client.delete(
            f'/store-admin/products/{product.id}/images/{image_id}/')
    assert delete_resp.status_code == status.HTTP_204_NO_CONTENT
    mock_delete_image.assert_called_once_with('products/1/x.png')
    assert not ProductImage.objects.filter(pk=image_id).exists()
