from unittest.mock import patch

from rest_framework.test import APIClient
from rest_framework import status
import pytest

from orders.models import Order


@pytest.fixture
def order():
    return Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_DELIVERY,
        guest_name='Guest',
        guest_email='guest@example.com',
        guest_phone='0800000000',
    )


def pay_successfully(order_id):
    client = APIClient()
    with patch('payment.serializers.initialize_transaction') as init_mock:
        init_mock.return_value = {'authorization_url': 'https://paystack.test/pay'}
        reference = client.post(
            '/store/payments/initialize/', {'order_id': order_id}).data['reference']
    with patch('payment.serializers.verify_transaction') as verify_mock:
        verify_mock.return_value = {'status': 'success'}
        client.post('/store/payments/verify/', {'reference': reference})


@pytest.mark.django_db
class TestTrackOrder:
    def test_newly_placed_unpaid_order_has_no_stage_yet(self, order):
        client = APIClient()
        response = client.post('/store/orders/lookup/', {
            'order_id': order.id, 'email': order.guest_email})
        assert response.data['status'] == ''

    def test_order_moves_to_confirmed_once_payment_succeeds(self, order):
        pay_successfully(order.id)

        client = APIClient()
        response = client.post('/store/orders/lookup/', {
            'order_id': order.id, 'email': order.guest_email})

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
