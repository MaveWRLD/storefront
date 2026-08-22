from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Variant
from cart.models import Cart, CartItem
from cart.test_helpers import bind_client_to_cart
from orders.models import Order

ADDRESS = {
    'recipient_name': 'Guest', 'email': 'guest@example.com', 'phone': '0800000000',
    'street_address': '12 Ring Rd', 'city': 'Accra', 'region': 'Greater Accra',
    'coordinates': {'lat': 5.6, 'lng': -0.2},
}


@pytest.fixture
def collection():
    return Collection.objects.create(title='Shirts')


@pytest.fixture
def variant(collection):
    product = Product.objects.create(
        title='Test Shirt', slug='test-shirt', collection=collection)
    return Variant.objects.create(
        product=product, sku='test-shirt', unit_price=1000, inventory=10)


@pytest.fixture
def cart_with_item(variant):
    cart = Cart.objects.create()
    CartItem.objects.create(cart=cart, variant=variant, quantity=1)
    return cart


def place_order(cart, payload):
    client = APIClient()
    bind_client_to_cart(client, cart)
    return client.post('/store-front/orders/', payload, format='json')


@pytest.mark.django_db
class TestDeliveryAddress:
    """CreateOrderSerializer requires and persists an address for any
    guest checkout (Order carries no contact fields of its own — address
    is the only place guest identity lives), and for DELIVERY orders
    specifically regardless of who places them — closing the gap where a
    delivery order could be placed and paid for with nowhere to ship it
    (gap-analysis doc, 'CreateOrder has no delivery-address fields')."""

    def test_delivery_order_without_address_is_rejected(self, cart_with_item):
        response = place_order(cart_with_item, {
            'fulfillment_method': Order.FULFILLMENT_DELIVERY,
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delivery_order_with_address_is_persisted(self, cart_with_item):
        response = place_order(cart_with_item, {
            'fulfillment_method': Order.FULFILLMENT_DELIVERY,
            'address': ADDRESS,
        })

        assert response.status_code == status.HTTP_200_OK
        order = Order.objects.get(pk=response.data['id'])
        assert order.shipping_address['city'] == 'Accra'
        assert order.shipping_address['coordinates'] == {'lat': 5.6, 'lng': -0.2}

    def test_guest_pickup_order_without_address_is_rejected(self, cart_with_item):
        # Order has no name/email/phone of its own — a guest PICKUP order
        # with no address would have zero identity anywhere on it.
        response = place_order(cart_with_item, {
            'fulfillment_method': Order.FULFILLMENT_PICKUP,
        })

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_guest_pickup_order_with_address_is_accepted(self, cart_with_item):
        response = place_order(cart_with_item, {
            'fulfillment_method': Order.FULFILLMENT_PICKUP,
            'address': ADDRESS,
        })

        assert response.status_code == status.HTTP_200_OK
