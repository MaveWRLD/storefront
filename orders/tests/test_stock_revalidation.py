from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, ProductStatus, Variant
from cart.models import Cart, CartItem
from orders.models import Order


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def make_product(collection):
    def _make(inventory=10, status=ProductStatus.PUBLISHED, **overrides):
        defaults = dict(title='Test Shirt', slug='test-shirt', collection=collection)
        defaults.update(overrides)
        product = Product.objects.create(status=status, **defaults)
        product.variant = Variant.objects.create(
            product=product, sku=defaults['slug'], unit_price=1000,
            inventory=inventory)
        return product
    return _make


@pytest.fixture
def cart():
    return Cart.objects.create()


def place_order(cart_id):
    client = APIClient()
    return client.post('/store/orders/', {
        'cart_id': str(cart_id),
        'fulfillment_method': Order.FULFILLMENT_DELIVERY,
        'guest_name': 'Guest',
        'guest_email': 'guest@example.com',
    })


@pytest.mark.django_db
class TestStockRevalidationAtCheckout:
    def test_all_items_available_creates_order_with_no_removed_items(self, cart, make_product):
        product = make_product(inventory=5)
        CartItem.objects.create(cart=cart, variant=product.variant, quantity=2)

        response = place_order(cart.id)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['items']) == 1
        assert response.data['unavailable_items'] == []

    def test_out_of_stock_item_flagged_and_removed_from_order(self, cart, make_product):
        available = make_product(
            title='Available', slug='available', inventory=5)
        out_of_stock = make_product(
            title='Sold Out', slug='sold-out', inventory=0)
        CartItem.objects.create(cart=cart, variant=available.variant, quantity=1)
        CartItem.objects.create(cart=cart, variant=out_of_stock.variant, quantity=1)

        response = place_order(cart.id)

        assert response.status_code == status.HTTP_200_OK
        order_product_titles = [i['variant']['product']['title']
                                for i in response.data['items']]
        assert order_product_titles == ['Available']
        assert len(response.data['unavailable_items']) == 1
        assert response.data['unavailable_items'][0]['title'] == 'Sold Out'

    def test_unpublished_item_flagged_and_removed_from_order(self, cart, make_product):
        available = make_product(
            title='Available', slug='available-2', inventory=5)
        draft = make_product(
            title='Not Yet Live', slug='not-yet-live', status=ProductStatus.DRAFT)
        CartItem.objects.create(cart=cart, variant=available.variant, quantity=1)
        CartItem.objects.create(cart=cart, variant=draft.variant, quantity=1)

        response = place_order(cart.id)

        assert response.status_code == status.HTTP_200_OK
        order_product_titles = [i['variant']['product']['title']
                                for i in response.data['items']]
        assert order_product_titles == ['Available']
        assert response.data['unavailable_items'][0]['title'] == 'Not Yet Live'

    def test_quantity_exceeding_current_stock_is_flagged(self, cart, make_product):
        product = make_product(inventory=1)
        CartItem.objects.create(cart=cart, variant=product.variant, quantity=3)

        response = place_order(cart.id)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_all_items_unavailable_rejects_with_no_order_created(self, cart, make_product):
        product = make_product(inventory=0)
        CartItem.objects.create(cart=cart, variant=product.variant, quantity=1)

        response = place_order(cart.id)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert Order.objects.count() == 0
