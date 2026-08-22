from unittest.mock import patch

from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Variant
from orders.models import Order, OrderItem
from shipping.gateways import ShippingProviderError

RATES_URL = '/store-front/shipping/rates/'
ADDRESS = {
    'recipient_name': 'Guest', 'email': 'guest@example.com', 'phone': '0800000000',
    'street_address': '12 Example Rd', 'city': 'Accra', 'region': 'Greater Accra',
    'coordinates': {'lat': 5.6037, 'lng': -0.1870},
}
ESTIMATE = {
    'cost': 25, 'estimated_delivery_at': 'Standard same day',
    'options': [
        {'priority': 'standard', 'cost': 25, 'description': 'Same day'},
        {'priority': 'economy', 'cost': 23, 'description': 'Next day'},
        {'priority': 'cargo', 'cost': 50, 'description': 'Heavy items'},
    ],
}


@pytest.fixture
def variant():
    product = Product.objects.create(
        title='Test Shirt', slug='test-shirt',
        collection=Collection.objects.create(title='Shirts'))
    return Variant.objects.create(
        product=product, sku='test-shirt', unit_price=1000, inventory=5)


@pytest.fixture
def delivery_order(variant):
    order = Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_DELIVERY,
        shipping_address=ADDRESS)
    OrderItem.objects.create(order=order, variant=variant, quantity=1, unit_price=variant.unit_price)
    return order


@pytest.fixture
def pickup_order(variant):
    order = Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_PICKUP,
        shipping_address=ADDRESS)
    OrderItem.objects.create(order=order, variant=variant, quantity=1, unit_price=variant.unit_price)
    return order


@pytest.mark.django_db
class TestRateQuote:
    """FR-001/FR-002/FR-003: a live shipping price + ETA before payment,
    delivery orders only, folded into the order total and persisted for
    booking (Dawurobo re-prices at booking time, so the address itself
    — not a quote token — is what's carried through). `options` is
    informational only: Dawurobo's booking call can't honor a
    customer-picked tier (shipping/gateways/dawurobo.py docstring)."""

    def test_delivery_order_gets_a_quote_with_cost_eta_and_tiers(self, delivery_order):
        client = APIClient()
        with patch('shipping.gateways.dawurobo.DawuroboGateway.get_rates') as mocked:
            mocked.return_value = ESTIMATE
            response = client.post(
                RATES_URL, {'order_id': delivery_order.id, 'address': ADDRESS}, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['cost'] == ESTIMATE['cost']
        assert response.data['estimated_delivery_at'] == ESTIMATE['estimated_delivery_at']
        assert response.data['options'] == ESTIMATE['options']

    def test_pickup_order_is_rejected(self, pickup_order):
        client = APIClient()
        response = client.post(
            RATES_URL, {'order_id': pickup_order.id, 'address': ADDRESS}, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unserviceable_address_is_rejected(self, delivery_order):
        client = APIClient()
        with patch('shipping.gateways.dawurobo.DawuroboGateway.get_rates') as mocked:
            mocked.side_effect = ShippingProviderError('Delivery is not available for this address.')
            response = client.post(
                RATES_URL, {'order_id': delivery_order.id, 'address': ADDRESS}, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_quote_persists_cost_and_address_onto_the_order(self, delivery_order):
        client = APIClient()
        with patch('shipping.gateways.dawurobo.DawuroboGateway.get_rates') as mocked:
            mocked.return_value = ESTIMATE
            response = client.post(
                RATES_URL, {'order_id': delivery_order.id, 'address': ADDRESS}, format='json')

        assert response.status_code == status.HTTP_200_OK
        delivery_order.refresh_from_db()
        assert delivery_order.shipping_cost.amount == 25
        assert delivery_order.shipping_address['coordinates'] == {'lat': 5.6037, 'lng': -0.187}
        assert delivery_order.get_total() == delivery_order.subtotal + delivery_order.shipping_cost
