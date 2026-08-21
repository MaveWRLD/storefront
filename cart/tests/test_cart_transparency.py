from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, ProductStatus, Variant
from cart.serializers import CartItemSerializer


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def make_product(collection):
    def _make(inventory=5, status=ProductStatus.PUBLISHED, unit_price=1000, **overrides):
        defaults = dict(title='Test Shirt', slug='test-shirt', collection=collection)
        defaults.update(overrides)
        product = Product.objects.create(status=status, **defaults)
        product.variant = Variant.objects.create(
            product=product, sku=defaults['slug'], unit_price=unit_price,
            inventory=inventory)
        return product
    return _make


@pytest.mark.django_db
class TestCartTransparency:
    """Cart transparency gap: GET cart now surfaces price_changed and a
    per-item ACTIVE/UNAVAILABLE status, instead of only rejecting at
    add-time or order-time."""

    def test_new_line_reports_no_price_change(self, make_product):
        product = make_product(unit_price=1000)
        client = APIClient()
        client.post('/store-front/cart/items/',
                     {'variant_id': product.variant.id, 'quantity': 1})

        response = client.get('/store-front/cart/')

        item = response.data['items'][0]
        assert item['price_changed'] is False
        assert item['status'] == CartItemSerializer.STATUS_ACTIVE

    def test_price_increase_after_add_is_flagged(self, make_product):
        product = make_product(unit_price=1000)
        client = APIClient()
        client.post('/store-front/cart/items/',
                     {'variant_id': product.variant.id, 'quantity': 1})

        Variant.objects.filter(pk=product.variant.id).update(unit_price=1500)

        response = client.get('/store-front/cart/')

        assert response.data['items'][0]['price_changed'] is True

    def test_line_that_goes_out_of_stock_is_flagged_unavailable(self, make_product):
        product = make_product(inventory=1, unit_price=1000)
        client = APIClient()
        client.post('/store-front/cart/items/',
                     {'variant_id': product.variant.id, 'quantity': 1})

        Variant.objects.filter(pk=product.variant.id).update(inventory=0)

        response = client.get('/store-front/cart/')

        assert response.data['items'][0]['status'] == CartItemSerializer.STATUS_UNAVAILABLE

    def test_line_whose_product_is_archived_is_flagged_unavailable(self, make_product):
        product = make_product(unit_price=1000)
        client = APIClient()
        client.post('/store-front/cart/items/',
                     {'variant_id': product.variant.id, 'quantity': 1})

        Product.objects.filter(pk=product.id).update(status=ProductStatus.ARCHIVED)

        response = client.get('/store-front/cart/')

        assert response.data['items'][0]['status'] == CartItemSerializer.STATUS_UNAVAILABLE

    def test_bumping_quantity_does_not_reset_the_price_snapshot(self, make_product):
        product = make_product(unit_price=1000)
        client = APIClient()
        client.post('/store-front/cart/items/',
                     {'variant_id': product.variant.id, 'quantity': 1})

        Variant.objects.filter(pk=product.variant.id).update(unit_price=1500)
        client.post('/store-front/cart/items/',
                     {'variant_id': product.variant.id, 'quantity': 1})

        response = client.get('/store-front/cart/')

        assert response.data['items'][0]['price_changed'] is True
