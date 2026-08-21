from rest_framework.test import APIClient
from rest_framework import serializers, status
import pytest

from catalog.models import Collection, Product, Variant
from cart.models import Cart, CartItem
from cart.test_helpers import bind_client_to_cart
from orders.models import Order
from orders.serializers import CreateOrderSerializer


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def make_product(collection):
    def _make(inventory=10, allocated=0, **overrides):
        defaults = dict(title='Test Shirt', slug='test-shirt', collection=collection)
        defaults.update(overrides)
        product = Product.objects.create(**defaults)
        product.variant = Variant.objects.create(
            product=product, sku=defaults['slug'], unit_price=1000,
            inventory=inventory, allocated=allocated)
        return product
    return _make


@pytest.fixture
def cart():
    return Cart.objects.create()


def place_order(cart):
    client = APIClient()
    bind_client_to_cart(client, cart)
    return client.post('/store-front/orders/', {
        'fulfillment_method': Order.FULFILLMENT_DELIVERY,
        'address': {
            'recipient_name': 'Guest', 'email': 'guest@example.com', 'phone': '0800000000',
            'street_address': '1 Test St', 'city': 'Accra', 'region': 'Greater Accra',
            'coordinates': {'lat': 5.6, 'lng': -0.2},
        },
    }, format='json')


@pytest.mark.django_db
class TestAllocateStockAtCheckout:
    """US-30: checkout allocates instead of decrementing. Business Rule
    (Warehouse): 'Stock decrements only on payment success, not at
    checkout' — Variant.inventory is untouched here; only `allocated`
    moves, and physical stock only drops later at payment success (US-31)."""

    def test_placing_order_bumps_allocated_and_leaves_inventory_untouched(self, cart, make_product):
        product = make_product(inventory=5)
        CartItem.objects.create(cart=cart, variant=product.variant, quantity=2)

        response = place_order(cart)

        assert response.status_code == status.HTTP_200_OK
        product.variant.refresh_from_db()
        assert product.variant.inventory == 5
        assert product.variant.allocated == 2

    def test_allocated_bumped_separately_per_line_across_variants(self, cart, make_product):
        first = make_product(title='Shirt A', slug='shirt-a', inventory=5)
        second = make_product(title='Shirt B', slug='shirt-b', inventory=3)
        CartItem.objects.create(cart=cart, variant=first.variant, quantity=2)
        CartItem.objects.create(cart=cart, variant=second.variant, quantity=1)

        response = place_order(cart)

        assert response.status_code == status.HTTP_200_OK
        first.variant.refresh_from_db()
        second.variant.refresh_from_db()
        assert first.variant.allocated == 2
        assert second.variant.allocated == 1

    def test_allocated_stock_is_no_longer_available_to_a_second_checkout(self, cart, make_product):
        product = make_product(inventory=1)
        CartItem.objects.create(cart=cart, variant=product.variant, quantity=1)
        place_order(cart)

        other_cart = Cart.objects.create()
        CartItem.objects.create(cart=other_cart, variant=product.variant, quantity=1)
        response = place_order(other_cart)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        product.variant.refresh_from_db()
        assert product.variant.allocated == 1

    def test_recheck_under_lock_rejects_stock_consumed_since_validate(self, cart, make_product):
        """Closes the checkout TOCTOU race: simulates another checkout
        allocating the last unit in the window between validate() (unlocked)
        and save() taking the row lock."""
        product = make_product(inventory=1)
        variant = product.variant
        item = CartItem.objects.create(cart=cart, variant=variant, quantity=1)

        # By the time save() runs, the unit has already been allocated
        # elsewhere — validate() had no way to see this.
        Variant.objects.filter(pk=variant.pk).update(allocated=1)

        serializer = CreateOrderSerializer()
        serializer._validated_data = {
            'fulfillment_method': Order.FULFILLMENT_DELIVERY,
            'address': {
                'recipient_name': 'Guest', 'email': 'guest@example.com', 'phone': '',
                'street_address': '1 Test St', 'city': 'Accra', 'region': 'Greater Accra',
                'coordinates': {'lat': 5.6, 'lng': -0.2},
            },
            '_cart': cart,
            '_available_items': [item],
            '_unavailable_items': [],
        }
        # save() only needs .session.pop(key, None) off the request — a
        # plain dict stands in fine, no real HttpRequest required here.
        serializer._context = {'user': None, 'request': type(
            'FakeRequest', (), {'session': {}})()}

        with pytest.raises(serializers.ValidationError):
            serializer.save()

        variant.refresh_from_db()
        assert variant.allocated == 1
        assert Order.objects.count() == 0
