import json
from io import BytesIO

from django.contrib.auth import get_user_model
from PIL import Image as PILImage
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Product, ProductAxis

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


def create_product_request(**overrides):
    data = {
        'name': 'New Shirt',
        'price': {'amount': 25.00, 'currency': 'GHS'},
        'axes': [
            {'name': 'Size', 'sortOrder': 0, 'allowedValues': [
                {'name': 'Small', 'code': 'S'}, {'name': 'Large', 'code': 'L'}]},
            {'name': 'Color', 'sortOrder': 1, 'allowedValues': [
                {'name': 'Red', 'code': 'R'}]},
        ],
    }
    data.update(overrides)
    return data


def post_product(client, data=None, images=None):
    if images is None:
        images = [make_image()]
    return client.post(
        '/store-admin/products/',
        {'data': json.dumps(create_product_request(**(data or {}))), 'images': images},
        format='multipart')


@pytest.mark.django_db
class TestCreateProduct:
    def test_anonymous_cannot_create_product(self):
        response = post_product(APIClient())
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_non_admin_cannot_create_product(self):
        client = APIClient()
        client.force_authenticate(user=User())
        response = post_product(client)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_creates_product_with_axes_and_image(self, admin_client):
        response = post_product(admin_client)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['slug'] == 'new-shirt'
        assert response.data['is_available'] is True
        # no variants at creation time (added via the sub-resource below)
        assert response.data['total_stock'] == 0
        assert len(response.data['images']) == 1
        assert {axis['name'] for axis in response.data['axes']} == {'Size', 'Color'}

        product = Product.objects.get(pk=response.data['id'])
        assert product.price.amount == 25
        assert str(product.price.currency) == 'GHS'
        assert product.collection is None
        size = product.axes.get(name='Size')
        assert set(size.values.values_list('name', flat=True)) == {'Small', 'Large'}

    def test_rejects_duplicate_product_name(self, admin_client):
        assert post_product(admin_client).status_code == status.HTTP_201_CREATED
        response = post_product(admin_client, images=[make_image('other.png')])
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_missing_name(self, admin_client):
        response = post_product(admin_client, data={'name': ''})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_price_not_greater_than_zero(self, admin_client):
        response = post_product(admin_client, data={'price': {'amount': 0, 'currency': 'GHS'}})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_unsupported_currency(self, admin_client):
        response = post_product(admin_client, data={'price': {'amount': 10, 'currency': 'USD'}})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_no_axes(self, admin_client):
        response = post_product(admin_client, data={'axes': []})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_axis_with_no_allowed_values(self, admin_client):
        response = post_product(admin_client, data={
            'axes': [{'name': 'Size', 'sortOrder': 0, 'allowedValues': []}]})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_no_images(self, admin_client):
        response = post_product(admin_client, images=[])
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_accepts_multiple_images(self, admin_client):
        response = post_product(admin_client, images=[make_image('a.png'), make_image('b.png')])
        assert response.status_code == status.HTTP_201_CREATED
        assert len(response.data['images']) == 2

    def test_admin_adds_variant_via_sub_resource_after_product_created(self, admin_client):
        create_response = post_product(admin_client)
        product_id = create_response.data['id']
        size_value = ProductAxis.objects.get(product_id=product_id, name='Size').values.get(name='Small')
        color_value = ProductAxis.objects.get(product_id=product_id, name='Color').values.get(name='Red')

        response = admin_client.post(
            f'/store-admin/products/{product_id}/variants/',
            {'sku': 'new-shirt-s-r', 'unit_price': 1500, 'inventory': 5,
             'axis_value_ids': [size_value.id, color_value.id]},
            format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['sku'] == 'new-shirt-s-r'
        product = Product.objects.get(pk=product_id)
        assert product.variants.count() == 1
        assert product.total_stock == 5

    def test_admin_can_attach_an_additional_image_to_a_product(self, admin_client):
        create_response = post_product(admin_client)
        product_id = create_response.data['id']

        response = admin_client.post(
            f'/store-admin/products/{product_id}/images/',
            {'image': make_image('extra.png'), 'alt_text': 'A shirt'},
            format='multipart')

        assert response.status_code == status.HTTP_201_CREATED

        detail = admin_client.get(f'/store-admin/products/{product_id}/')
        assert len(detail.data['images']) == 2

    def test_non_admin_cannot_attach_image(self, admin_client):
        create_response = post_product(admin_client)
        product_id = create_response.data['id']

        client = APIClient()
        response = client.post(
            f'/store-admin/products/{product_id}/images/', {'alt_text': 'nope'})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
