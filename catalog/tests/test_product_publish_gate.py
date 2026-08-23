from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, ProductImage, ProductStatus, Variant

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
def draft_product(collection):
    return Product.objects.create(
        title='Test Shirt', slug='test-shirt', collection=collection,
        status=ProductStatus.DRAFT)


@pytest.mark.django_db
class TestProductPublishGate:
    def test_publish_rejected_when_product_has_no_own_image(self, admin_client, draft_product):
        response = admin_client.patch(
            f'/store-admin/products/{draft_product.id}/',
            {'status': 'published'}, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'image' in str(response.data['status']).lower()
        draft_product.refresh_from_db()
        assert draft_product.status == ProductStatus.DRAFT

    def test_publish_rejected_when_a_variant_has_no_image(self, admin_client, draft_product):
        ProductImage.objects.create(product=draft_product, image_key='gallery.png')
        variant = Variant.objects.create(
            product=draft_product, sku='test-shirt-s', unit_price=1000)

        response = admin_client.patch(
            f'/store-admin/products/{draft_product.id}/',
            {'status': 'published'}, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert variant.sku in str(response.data['status'])

    def test_publish_succeeds_when_product_and_every_variant_have_images(
            self, admin_client, draft_product):
        ProductImage.objects.create(product=draft_product, image_key='gallery.png')
        variant = Variant.objects.create(
            product=draft_product, sku='test-shirt-s', unit_price=1000)
        ProductImage.objects.create(
            product=draft_product, image_key='variant.png', variant=variant)

        response = admin_client.patch(
            f'/store-admin/products/{draft_product.id}/',
            {'status': 'published'}, format='json')

        assert response.status_code == status.HTTP_200_OK
        draft_product.refresh_from_db()
        assert draft_product.status == ProductStatus.PUBLISHED

    def test_updating_unrelated_field_without_touching_status_is_unaffected(
            self, admin_client, draft_product):
        response = admin_client.patch(
            f'/store-admin/products/{draft_product.id}/',
            {'title': 'Renamed Shirt'}, format='json')

        assert response.status_code == status.HTTP_200_OK
