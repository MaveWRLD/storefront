from unittest.mock import patch

from rest_framework.test import APIClient
from rest_framework import status
import pytest

from orders.models import Order
from payment.models import Payment


@pytest.fixture
def order():
    return Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_DELIVERY,
        shipping_cost=500,  # simulates a completed /shipping/rates/ quote
        shipping_address={
        'recipient_name': 'Guest', 'email': 'guest@example.com',
        'phone': '0800000000', 'street_address': '1 Test St',
        'city': 'Accra', 'region': 'Greater Accra',
        'coordinates': {'lat': 5.6, 'lng': -0.2},
    },
    )


def initialize(order):
    client = APIClient()
    with patch('payment.gateways.paystack.PaystackGateway.initialize_transaction') as mocked:
        mocked.return_value = {'authorization_url': 'https://paystack.test/pay'}
        return client.post('/store-front/payments/initialize/', {
            'order_id': order.id, 'guest_token': order.guest_token})


def verify_as(reference, outcome_status, guest_token):
    client = APIClient()
    with patch('payment.gateways.paystack.PaystackGateway.verify_transaction') as mocked:
        mocked.return_value = {'status': outcome_status}
        return client.post('/store-front/payments/verify/', {
            'reference': reference, 'guest_token': guest_token})


@pytest.mark.django_db
class TestRetryFailedPayment:
    def test_retry_after_failure_creates_a_new_payment_against_the_same_order(self, order):
        first = initialize(order)
        verify_as(first.data['reference'], 'failed', order.guest_token)

        second = initialize(order)

        assert second.status_code == status.HTTP_200_OK
        assert second.data['reference'] != first.data['reference']
        assert Payment.objects.filter(order=order).count() == 2

    def test_order_stays_open_after_failed_payment_so_it_can_be_retried(self, order):
        first = initialize(order)
        verify_as(first.data['reference'], 'failed', order.guest_token)

        order.refresh_from_db()
        assert order.payment_status == Order.PAYMENT_STATUS_PENDING

    def test_retries_are_not_capped(self, order):
        for _ in range(5):
            attempt = initialize(order)
            assert attempt.status_code == status.HTTP_200_OK
            verify_as(attempt.data['reference'], 'failed', order.guest_token)

        assert Payment.objects.filter(order=order).count() == 5
        order.refresh_from_db()
        assert order.payment_status == Order.PAYMENT_STATUS_PENDING

    def test_cannot_retry_once_payment_already_succeeded(self, order):
        first = initialize(order)
        verify_as(first.data['reference'], 'success', order.guest_token)

        again = initialize(order)

        assert again.status_code == status.HTTP_400_BAD_REQUEST
        order.refresh_from_db()
        assert order.payment_status == Order.PAYMENT_STATUS_COMPLETE

    def test_successful_retry_after_prior_failures_completes_the_order(self, order):
        first = initialize(order)
        verify_as(first.data['reference'], 'failed', order.guest_token)

        second = initialize(order)
        verify_as(second.data['reference'], 'success', order.guest_token)

        order.refresh_from_db()
        assert order.payment_status == Order.PAYMENT_STATUS_COMPLETE
