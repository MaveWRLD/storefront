from unittest.mock import patch

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


def pay_successfully(order):
    client = APIClient()
    with patch('payment.gateways.paystack.PaystackGateway.initialize_transaction') as init_mock:
        init_mock.return_value = {'authorization_url': 'https://paystack.test/pay'}
        reference = client.post(
            '/store-front/payments/initialize/',
            {'order_id': order.id, 'guest_token': order.guest_token}).data['reference']
    with patch('payment.gateways.paystack.PaystackGateway.verify_transaction') as verify_mock:
        verify_mock.return_value = {'status': 'success'}
        client.post('/store-front/payments/verify/', {
            'reference': reference, 'guest_token': order.guest_token})


@pytest.mark.django_db
class TestTrackOrder:
    def test_newly_placed_unpaid_order_has_no_stage_yet(self, order):
        client = APIClient()
        response = client.post('/store-front/orders/lookup/', {
            'order_id': order.id, 'email': order.get_email()})
        assert response.data['status'] == ''

    def test_order_moves_to_confirmed_once_payment_succeeds(self, order):
        pay_successfully(order)

        client = APIClient()
        response = client.post('/store-front/orders/lookup/', {
            'order_id': order.id, 'email': order.get_email()})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == Order.STATUS_CONFIRMED

    def test_status_is_one_of_the_defined_fulfillment_stages(self):
        stage_values = dict(Order.STATUS_CHOICES)
        assert set(stage_values) == {
            Order.STATUS_CONFIRMED, Order.STATUS_FULFILLMENT,
            Order.STATUS_READY_FOR_PICKUP, Order.STATUS_OUT_FOR_DELIVERY,
            Order.STATUS_COMPLETED, Order.STATUS_DELIVERY_FAILED,
            Order.STATUS_PENDING_RESOLUTION, Order.STATUS_CANCELLED,
        }
