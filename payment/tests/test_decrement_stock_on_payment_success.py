from unittest.mock import patch

from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Variant
from orders.models import Order, OrderItem
from payment.models import Payment


@pytest.fixture
def variant():
    product = Product.objects.create(
        title='Test Shirt', slug='test-shirt',
        collection=Collection.objects.create(title='Shirts'))
    # allocated=2 simulates the checkout-time allocation (US-30) this
    # payment is confirming.
    return Variant.objects.create(
        product=product, sku='test-shirt', unit_price=1000,
        inventory=5, allocated=2)


@pytest.fixture
def order(variant):
    order = Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_DELIVERY,
        shipping_address={
        'recipient_name': 'Guest', 'email': 'guest@example.com',
        'phone': '0800000000', 'street_address': '1 Test St',
        'city': 'Accra', 'region': 'Greater Accra',
        'coordinates': {'lat': 5.6, 'lng': -0.2},
    },
    )
    OrderItem.objects.create(
        order=order, variant=variant, quantity=2, unit_price=variant.unit_price)
    return order


def initialize(order_id):
    client = APIClient()
    with patch('payment.gateways.paystack.PaystackGateway.initialize_transaction') as mocked:
        mocked.return_value = {'authorization_url': 'https://paystack.test/pay'}
        return client.post('/store-front/payments/initialize/', {'order_id': order_id})


def verify_as(reference, outcome_status):
    client = APIClient()
    with patch('payment.gateways.paystack.PaystackGateway.verify_transaction') as mocked:
        mocked.return_value = {'status': outcome_status}
        return client.post('/store-front/payments/verify/', {'reference': reference})


@pytest.mark.django_db
class TestDecrementStockOnPaymentSuccess:
    """US-31: payment success is the only place Variant.inventory
    physically drops. Business Rule (Warehouse): 'Stock decrements only on
    payment success, not at checkout' — inventory and allocated move
    together, by the order line's quantity."""

    def test_successful_payment_decrements_inventory_and_releases_allocated(self, order, variant):
        payment = initialize(order.id)

        response = verify_as(payment.data['reference'], 'success')

        assert response.status_code == status.HTTP_200_OK
        variant.refresh_from_db()
        assert variant.inventory == 3
        assert variant.allocated == 0

    def test_failed_payment_leaves_inventory_and_allocated_untouched(self, order, variant):
        payment = initialize(order.id)

        response = verify_as(payment.data['reference'], 'failed')

        assert response.status_code == status.HTTP_200_OK
        variant.refresh_from_db()
        assert variant.inventory == 5
        assert variant.allocated == 2

    def test_untracked_variant_is_not_decremented_on_success(self, order, variant):
        Variant.objects.filter(pk=variant.pk).update(
            track_inventory=False, inventory=0, allocated=0)
        payment = initialize(order.id)

        response = verify_as(payment.data['reference'], 'success')

        assert response.status_code == status.HTTP_200_OK
        variant.refresh_from_db()
        assert variant.inventory == 0
        assert variant.allocated == 0

    def test_order_confirmed_on_success(self, order):
        payment = initialize(order.id)

        verify_as(payment.data['reference'], 'success')

        order.refresh_from_db()
        assert order.payment_status == Order.PAYMENT_STATUS_COMPLETE
        assert order.status == Order.STATUS_CONFIRMED
        assert Payment.objects.get(reference=payment.data['reference']).status == Payment.STATUS_SUCCESS
