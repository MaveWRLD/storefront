from io import BytesIO

from django.contrib.auth import get_user_model
from PIL import Image as PILImage
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from catalog.models import (
    AxisValue, Collection, Product, ProductAxis, ProductImage, Variant,
)

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
def size_axis(product):
    return ProductAxis.objects.create(product=product, name='Size', sort_order=0)


@pytest.fixture
def small(size_axis):
    return AxisValue.objects.create(axis=size_axis, name='Small', code='S')


@pytest.fixture
def large(size_axis):
    return AxisValue.objects.create(axis=size_axis, name='Large', code='L')


def make_image(name='test.png'):
    buf = BytesIO()
    PILImage.new('RGB', (10, 10)).save(buf, format='PNG')
    buf.seek(0)
    buf.name = name
    return buf


@pytest.mark.django_db
class TestVariantBatchCreate:
    def test_creates_multiple_variants_in_one_request(self, admin_client, product, small, large):
        response = admin_client.post(
            f'/store-admin/products/{product.id}/variants/batch/',
            [
                {'sku': 'test-shirt-s', 'unit_price': 1000, 'axis_value_ids': [small.id]},
                {'sku': 'test-shirt-l', 'unit_price': 1200, 'axis_value_ids': [large.id]},
            ],
            format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert {v['sku'] for v in response.data} == {'test-shirt-s', 'test-shirt-l'}
        assert product.variants.count() == 2

    def test_empty_batch_rejected(self, admin_client, product):
        response = admin_client.post(
            f'/store-admin/products/{product.id}/variants/batch/', [], format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_list_payload_rejected(self, admin_client, product):
        response = admin_client.post(
            f'/store-admin/products/{product.id}/variants/batch/',
            {'sku': 'test-shirt-s', 'unit_price': 1000}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_one_invalid_item_rejects_whole_batch(self, admin_client, product, small, large):
        response = admin_client.post(
            f'/store-admin/products/{product.id}/variants/batch/',
            [
                {'sku': 'test-shirt-s', 'unit_price': 1000, 'axis_value_ids': [small.id]},
                {'sku': 'test-shirt-l', 'unit_price': -5, 'axis_value_ids': [large.id]},
            ],
            format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert product.variants.count() == 0

    def test_duplicate_sku_within_batch_rejects_whole_batch(self, admin_client, product, small, large):
        response = admin_client.post(
            f'/store-admin/products/{product.id}/variants/batch/',
            [
                {'sku': 'dup-sku', 'unit_price': 1000, 'axis_value_ids': [small.id]},
                {'sku': 'dup-sku', 'unit_price': 1200, 'axis_value_ids': [large.id]},
            ],
            format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert product.variants.count() == 0

    def test_duplicate_combination_within_batch_rejects_whole_batch(
            self, admin_client, product, small):
        response = admin_client.post(
            f'/store-admin/products/{product.id}/variants/batch/',
            [
                {'sku': 'a', 'unit_price': 1000, 'axis_value_ids': [small.id]},
                {'sku': 'b', 'unit_price': 1000, 'axis_value_ids': [small.id]},
            ],
            format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert product.variants.count() == 0

    def test_duplicate_combination_against_existing_variant_rejects_whole_batch(
            self, admin_client, product, small, large):
        from catalog.models import VariantAxisValue
        existing = Variant.objects.create(product=product, sku='existing', unit_price=1000)
        VariantAxisValue.objects.create(variant=existing, axis_value=small)

        response = admin_client.post(
            f'/store-admin/products/{product.id}/variants/batch/',
            [{'sku': 'new-one', 'unit_price': 1000, 'axis_value_ids': [small.id]}],
            format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert product.variants.count() == 1


@pytest.mark.django_db
class TestPerVariantImages:
    def test_admin_attaches_image_to_a_specific_variant(self, admin_client, product, small):
        variant = Variant.objects.create(product=product, sku='test-shirt-s', unit_price=1000)

        response = admin_client.post(
            f'/store-admin/products/{product.id}/images/',
            {'image': make_image(), 'alt_text': 'S on model', 'variant': variant.id},
            format='multipart')

        assert response.status_code == status.HTTP_201_CREATED
        image = ProductImage.objects.get(pk=response.data['id'])
        assert image.variant_id == variant.id
        assert image.product_id == product.id

    def test_rejects_variant_from_another_product(self, admin_client, product, collection):
        other_product = Product.objects.create(
            title='Other', slug='other', collection=collection)
        other_variant = Variant.objects.create(
            product=other_product, sku='other-sku', unit_price=1000)

        response = admin_client.post(
            f'/store-admin/products/{product.id}/images/',
            {'image': make_image(), 'variant': other_variant.id},
            format='multipart')

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_both_axis_value_and_variant_on_same_image(
            self, admin_client, product, small, size_axis):
        variant = Variant.objects.create(product=product, sku='test-shirt-s', unit_price=1000)

        response = admin_client.post(
            f'/store-admin/products/{product.id}/images/',
            {'image': make_image(), 'variant': variant.id, 'axis_value': small.id},
            format='multipart')

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_storefront_product_detail_exposes_variant_images(self, product, small):
        variant = Variant.objects.create(product=product, sku='test-shirt-s', unit_price=1000)
        ProductImage.objects.create(
            product=product, variant=variant, image_key='products/1/variants/1/test.png')

        response = APIClient().get(f'/store-front/products/{product.slug}/')
        assert response.status_code == status.HTTP_200_OK
        variant_data = next(v for v in response.data['variants'] if v['id'] == variant.id)
        assert any(img['object_key'] == 'products/1/variants/1/test.png'
                   for img in variant_data['images'])
        assert not any(img['object_key'] == 'products/1/variants/1/test.png'
                       for img in response.data['images'])
