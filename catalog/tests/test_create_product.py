from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, ProductStatus

User = get_user_model()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


def product_payload(collection, **overrides):
    payload = dict(
        title='New Shirt',
        slug='new-shirt',
        description='A shirt',
        collection=collection.id,
        variants=[{'sku': 'new-shirt', 'unit_price': 1500, 'inventory': 5}],
    )
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestCreateProduct:
    def test_anonymous_cannot_create_product(self, collection):
        client = APIClient()
        response = client.post(
            '/store-admin/products/', product_payload(collection), format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_non_admin_cannot_create_product(self, collection):
        client = APIClient()
        client.force_authenticate(user=User())
        response = client.post(
            '/store-admin/products/', product_payload(collection), format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_creates_product_with_name_and_price_appears_available(self, admin_client, collection):
        response = admin_client.post(
            '/store-admin/products/', product_payload(collection), format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['is_available'] is True
        assert response.data['variants'][0]['sku'] == 'new-shirt'
        product = Product.objects.get(pk=response.data['id'])
        assert product.status == ProductStatus.PUBLISHED

    def test_admin_can_mark_new_product_unavailable(self, admin_client, collection):
        response = admin_client.post(
            '/store-admin/products/',
            product_payload(collection, status=ProductStatus.DRAFT), format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['is_available'] is False

    def test_missing_title_returns_400(self, admin_client, collection):
        payload = product_payload(collection)
        del payload['title']
        response = admin_client.post('/store-admin/products/', payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'title' in response.data

    def test_missing_price_returns_400(self, admin_client, collection):
        payload = product_payload(collection)
        del payload['variants'][0]['unit_price']
        response = admin_client.post('/store-admin/products/', payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'unit_price' in response.data['variants'][0]

    def test_missing_variants_returns_400(self, admin_client, collection):
        payload = product_payload(collection)
        del payload['variants']
        response = admin_client.post('/store-admin/products/', payload, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'variants' in response.data

    def test_admin_can_attach_an_image_to_a_product(self, admin_client, collection):
        create_response = admin_client.post(
            '/store-admin/products/', product_payload(collection), format='json')
        product_id = create_response.data['id']

        from io import BytesIO
        from PIL import Image as PILImage
        buf = BytesIO()
        PILImage.new('RGB', (10, 10)).save(buf, format='PNG')
        buf.seek(0)
        buf.name = 'test.png'

        response = admin_client.post(
            f'/store-admin/products/{product_id}/images/',
            {'image': buf, 'alt_text': 'A shirt'},
            format='multipart')

        assert response.status_code == status.HTTP_201_CREATED

        detail = admin_client.get(f'/store-admin/products/{product_id}/')
        assert len(detail.data['images']) == 1
        assert detail.data['images'][0]['alt_text'] == 'A shirt'

    def test_non_admin_cannot_attach_image(self, admin_client, collection):
        create_response = admin_client.post(
            '/store-admin/products/', product_payload(collection), format='json')
        product_id = create_response.data['id']

        client = APIClient()
        response = client.post(
            f'/store-admin/products/{product_id}/images/', {'alt_text': 'nope'})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
