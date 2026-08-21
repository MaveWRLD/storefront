from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
import pytest

from notifications.models import Notification
from orders.models import Order

User = get_user_model()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


@pytest.fixture
def make_order():
    def _make(fulfillment_method, order_status=Order.STATUS_CONFIRMED):
        return Order.objects.create(
            fulfillment_method=fulfillment_method,
            payment_status=Order.PAYMENT_STATUS_COMPLETE,
            status=order_status,
            shipping_address={
        'recipient_name': 'Guest', 'email': 'guest@example.com',
        'phone': '0800000000', 'street_address': '1 Test St',
        'city': 'Accra', 'region': 'Greater Accra',
        'coordinates': {'lat': 5.6, 'lng': -0.2},
    },
        )
    return _make


def initialize_and_pay(order_id, outcome_status='success'):
    client = APIClient()
    with patch('payment.gateways.paystack.PaystackGateway.initialize_transaction') as mocked:
        mocked.return_value = {'authorization_url': 'https://paystack.test/pay'}
        init_response = client.post('/store-front/payments/initialize/', {'order_id': order_id})
    with patch('payment.gateways.paystack.PaystackGateway.verify_transaction') as mocked:
        mocked.return_value = {'status': outcome_status}
        client.post('/store-front/payments/verify/', {'reference': init_response.data['reference']})


@pytest.mark.django_db
class TestOrderMilestoneNotifications:
    """US-18: Business Rule (Notifications) 'Customer notified at every
    status-changing milestone'."""

    def test_payment_success_notifies_order_confirmed(self):
        order = Order.objects.create(
            fulfillment_method=Order.FULFILLMENT_PICKUP,
            shipping_address={
        'recipient_name': 'Guest', 'email': 'guest@example.com',
        'phone': '0800000000', 'street_address': '1 Test St',
        'city': 'Accra', 'region': 'Greater Accra',
        'coordinates': {'lat': 5.6, 'lng': -0.2},
    },
        )

        initialize_and_pay(order.id, 'success')

        assert Notification.objects.filter(
            order=order, event_type=Notification.EVENT_ORDER_CONFIRMED).exists()

    def test_payment_failure_does_not_notify_order_confirmed(self):
        order = Order.objects.create(
            fulfillment_method=Order.FULFILLMENT_PICKUP,
            shipping_address={
        'recipient_name': 'Guest', 'email': 'guest@example.com',
        'phone': '0800000000', 'street_address': '1 Test St',
        'city': 'Accra', 'region': 'Greater Accra',
        'coordinates': {'lat': 5.6, 'lng': -0.2},
    },
        )

        initialize_and_pay(order.id, 'failed')

        assert not Notification.objects.filter(
            order=order, event_type=Notification.EVENT_ORDER_CONFIRMED).exists()

    def test_marking_ready_for_pickup_notifies_customer(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_PICKUP)

        admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_READY_FOR_PICKUP})

        assert Notification.objects.filter(
            order=order, event_type=Notification.EVENT_READY_FOR_PICKUP).exists()

    def test_marking_out_for_delivery_notifies_customer(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_DELIVERY)

        admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_OUT_FOR_DELIVERY})

        assert Notification.objects.filter(
            order=order, event_type=Notification.EVENT_OUT_FOR_DELIVERY).exists()

    def test_marking_completed_notifies_delivered(self, admin_client, make_order):
        order = make_order(
            Order.FULFILLMENT_DELIVERY, order_status=Order.STATUS_OUT_FOR_DELIVERY)

        admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_COMPLETED})

        assert Notification.objects.filter(
            order=order, event_type=Notification.EVENT_DELIVERED).exists()
