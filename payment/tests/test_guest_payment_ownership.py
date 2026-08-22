from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from customers.models import Customer
from orders.models import Order

User = get_user_model()


@pytest.fixture
def guest_order():
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


@pytest.fixture
def customer_order(db):
    user = User.objects.create_user(email='owner@example.com', password='pw12345')
    customer = Customer.objects.get(user=user)
    return customer, Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_PICKUP, customer=customer)


def initialize(client, order_id, guest_token=None):
    payload = {'order_id': order_id}
    if guest_token is not None:
        payload['guest_token'] = guest_token
    with patch('payment.gateways.paystack.PaystackGateway.initialize_transaction') as mocked:
        mocked.return_value = {'authorization_url': 'https://paystack.test/pay'}
        return client.post('/store-front/payments/initialize/', payload)


def verify(client, reference, guest_token=None):
    payload = {'reference': reference}
    if guest_token is not None:
        payload['guest_token'] = guest_token
    with patch('payment.gateways.paystack.PaystackGateway.verify_transaction') as mocked:
        mocked.return_value = {'status': 'success'}
        return client.post('/store-front/payments/verify/', payload)


@pytest.mark.django_db
class TestGuestPaymentOwnership:
    def test_order_serializer_includes_guest_token_only_when_flagged(self, guest_order):
        from orders.serializers import OrderSerializer

        with_flag = OrderSerializer(guest_order, context={'include_guest_token': True}).data
        without_flag = OrderSerializer(guest_order).data

        assert with_flag['guest_token'] == guest_order.guest_token
        assert 'guest_token' not in without_flag

    def test_initialize_rejects_missing_guest_token_for_guest_order(self, guest_order):
        response = initialize(APIClient(), guest_order.id)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_initialize_rejects_wrong_guest_token(self, guest_order):
        response = initialize(APIClient(), guest_order.id, guest_token='00000000-0000-0000-0000-000000000000')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_initialize_accepts_correct_guest_token(self, guest_order):
        response = initialize(APIClient(), guest_order.id, guest_token=guest_order.guest_token)
        assert response.status_code == status.HTTP_200_OK

    def test_verify_rejects_wrong_guest_token(self, guest_order):
        init_response = initialize(APIClient(), guest_order.id, guest_token=guest_order.guest_token)
        response = verify(
            APIClient(), init_response.data['reference'],
            guest_token='00000000-0000-0000-0000-000000000000')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_verify_accepts_correct_guest_token(self, guest_order):
        init_response = initialize(APIClient(), guest_order.id, guest_token=guest_order.guest_token)
        response = verify(
            APIClient(), init_response.data['reference'], guest_token=guest_order.guest_token)
        assert response.status_code == status.HTTP_200_OK

    def test_initialize_rejects_non_owner_for_authenticated_order(self, customer_order):
        _, order = customer_order
        other = User.objects.create_user(email='other@example.com', password='pw12345')
        client = APIClient()
        client.force_authenticate(user=other)

        response = initialize(client, order.id)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_initialize_rejects_anonymous_for_authenticated_order(self, customer_order):
        _, order = customer_order
        response = initialize(APIClient(), order.id)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_initialize_accepts_owner_for_authenticated_order(self, customer_order):
        customer, order = customer_order
        client = APIClient()
        client.force_authenticate(user=customer.user)

        response = initialize(client, order.id)
        assert response.status_code == status.HTTP_200_OK
