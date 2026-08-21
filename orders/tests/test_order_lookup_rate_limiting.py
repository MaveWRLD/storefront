from rest_framework.test import APIClient
from rest_framework import status
import pytest

from orders.models import Order


@pytest.fixture
def order():
    return Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_DELIVERY,
        shipping_address={
        'recipient_name': 'Guest', 'email': 'guest@example.com',
        'phone': '0800000000', 'street_address': '1 Test St',
        'city': 'Accra', 'region': 'Greater Accra',
        'coordinates': {'lat': 5.6, 'lng': -0.2},
    },
    )


@pytest.mark.django_db
class TestOrderLookupRateLimiting:
    """Gap-analysis doc: 'No rate limiting anywhere' — guest order lookup
    is a bare order-id + email match, exactly the kind of endpoint brute
    force/enumeration targets. Spring runs 20/min, IP-keyed; matched here
    via the 'order-lookup' ScopedRateThrottle scope."""

    def test_lookup_is_rate_limited_after_20_per_minute(self, order):
        client = APIClient()
        for _ in range(20):
            response = client.post('/store-front/orders/lookup/', {
                'order_id': order.id, 'email': 'wrong@example.com'})
            assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = client.post('/store-front/orders/lookup/', {
            'order_id': order.id, 'email': 'wrong@example.com'})
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_order_create_is_not_throttled_by_the_lookup_scope(self):
        # create shares AllowAny with lookup but isn't the enumeration
        # surface — must not share its throttle scope.
        from cart.models import Cart, CartItem
        from cart.test_helpers import bind_client_to_cart
        from catalog.models import Collection, Product, Variant

        collection = Collection.objects.create(title='Shirts')
        product = Product.objects.create(
            title='Test Shirt', slug='test-shirt', collection=collection)
        variant = Variant.objects.create(
            product=product, sku='test-shirt', unit_price=1000,
            track_inventory=False, inventory=0)

        for _ in range(21):
            cart = Cart.objects.create()
            CartItem.objects.create(cart=cart, variant=variant, quantity=1)
            client = APIClient()
            bind_client_to_cart(client, cart)
            response = client.post('/store-front/orders/', {
                'fulfillment_method': Order.FULFILLMENT_PICKUP,
                'address': {
                    'recipient_name': 'Guest', 'email': 'guest@example.com', 'phone': '0800000000',
                    'street_address': '1 Test St', 'city': 'Accra', 'region': 'Greater Accra',
                    'coordinates': {'lat': 5.6, 'lng': -0.2},
                },
            }, format='json')
            assert response.status_code == status.HTTP_200_OK
