from io import BytesIO
from django.contrib.auth import get_user_model
from PIL import Image as PILImage
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import AxisValue, Collection, Product, ProductAxis

User = get_user_model()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def product(collection):
    return Product.objects.create(
        title='Test Shirt', slug='test-shirt', collection=collection)


@pytest.fixture
def color_axis(product):
    return ProductAxis.objects.create(product=product, name='Color')


@pytest.fixture
def red(color_axis):
    return AxisValue.objects.create(axis=color_axis, name='Red', code='red')


def png_file():
    buf = BytesIO()
    PILImage.new('RGB', (10, 10)).save(buf, format='PNG')
    buf.seek(0)
    buf.name = 'test.png'
    return buf


@pytest.mark.django_db
class TestAxisValueImages:
    """Per-axis-value images: an image tagged with an axis_value is a
    swatch-specific photo (e.g. the red variant's own shots), used for
    photo-switching — closing the gap where AxisValue carried no image
    relation at all."""

    def test_image_can_be_tagged_to_an_axis_value(self, admin_client, product, red):
        response = admin_client.post(
            f'/store-admin/products/{product.id}/images/',
            {'image': png_file(), 'alt_text': 'Red shirt', 'axis_value': red.id},
            format='multipart')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['axis_value'] == red.id

    def test_image_without_axis_value_is_a_general_product_photo(self, admin_client, product):
        response = admin_client.post(
            f'/store-admin/products/{product.id}/images/',
            {'image': png_file(), 'alt_text': 'General shot'},
            format='multipart')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['axis_value'] is None

    def test_axis_value_from_another_product_is_rejected(self, admin_client, product, collection):
        other_product = Product.objects.create(
            title='Other Shirt', slug='other-shirt', collection=collection)
        other_axis = ProductAxis.objects.create(product=other_product, name='Color')
        other_value = AxisValue.objects.create(axis=other_axis, name='Blue', code='blue')

        response = admin_client.post(
            f'/store-admin/products/{product.id}/images/',
            {'image': png_file(), 'axis_value': other_value.id},
            format='multipart')

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_axis_value_images_appear_nested_under_the_value(self, red):
        from catalog.models import ProductImage
        ProductImage.objects.create(
            product=red.axis.product,
            image_key='products/1/test.png',
            axis_value=red)

        assert red.images.count() == 1
