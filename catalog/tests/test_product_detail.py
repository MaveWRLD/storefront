from decimal import Decimal

from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, ProductStatus, Variant


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def make_product(collection):
    def _make(inventory=10, **overrides):
        defaults = dict(
            title='Test Shirt', slug='test-shirt', description='A shirt',
            collection=collection)
        defaults.update(overrides)
        product = Product.objects.create(**defaults)
        Variant.objects.create(
            product=product, sku=defaults['slug'], unit_price=1000,
            inventory=inventory)
        return product
    return _make


@pytest.mark.django_db
class TestProductDetail:
    def test_detail_returns_images_description_price_and_stock_status(self, make_product):
        product = make_product()
        client = APIClient()
        response = client.get(f'/store-front/products/{product.slug}/')

        assert response.status_code == status.HTTP_200_OK
        for field in ('images', 'description', 'variants', 'in_stock', 'is_available'):
            assert field in response.data
        assert 'unit_price' in response.data['variants'][0]

    def test_in_stock_true_when_inventory_positive(self, make_product):
        product = make_product(inventory=3)
        client = APIClient()
        response = client.get(f'/store-front/products/{product.slug}/')
        assert response.data['in_stock'] is True

    def test_in_stock_false_when_inventory_zero(self, make_product):
        product = make_product(inventory=0)
        client = APIClient()
        response = client.get(f'/store-front/products/{product.slug}/')
        assert response.data['in_stock'] is False

    def test_unpublished_product_detail_is_marked_not_available(self, make_product):
        product = make_product(status=ProductStatus.DRAFT)
        client = APIClient()
        response = client.get(f'/store-front/products/{product.slug}/')
        assert response.data['is_available'] is False

    def test_unknown_product_returns_404_not_error(self, make_product):
        client = APIClient()
        response = client.get('/store-front/products/999999/')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_variant_available_is_inventory_minus_allocated(self, make_product):
        product = make_product(inventory=5)
        variant = product.variants.get()
        variant.allocated = 2
        variant.save()
        client = APIClient()
        response = client.get(f'/store-front/products/{product.slug}/')
        assert response.data['variants'][0]['available'] == 3

    def test_variant_price_with_tax_is_exact_no_float_drift(self, make_product):
        """Decimal(1.1) built from a float literal isn't exactly 1.1 and
        can drift; Decimal('1.1') on Money math must not."""
        product = make_product(inventory=1)
        variant = product.variants.get()
        variant.unit_price = 999
        variant.save()
        client = APIClient()
        response = client.get(f'/store-front/products/{product.slug}/')
        assert response.data['variants'][0]['price_with_tax'] == Decimal('1098.90')
