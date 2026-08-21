from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from orders.models import Order

User = get_user_model()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


@pytest.fixture
def guest_order():
    return Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_PICKUP,
        payment_status=Order.PAYMENT_STATUS_COMPLETE,
        status=Order.STATUS_CONFIRMED,
        shipping_address={
        'recipient_name': 'Guest One', 'email': 'guest1@example.com',
        'phone': '0800000000', 'street_address': '1 Test St',
        'city': 'Accra', 'region': 'Greater Accra',
        'coordinates': {'lat': 5.6, 'lng': -0.2},
    },
    )


@pytest.fixture
def another_guest_order():
    return Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_DELIVERY,
        shipping_address={
        'recipient_name': 'Guest Two', 'email': 'guest2@example.com',
        'phone': '0800000001', 'street_address': '1 Test St',
        'city': 'Accra', 'region': 'Greater Accra',
        'coordinates': {'lat': 5.6, 'lng': -0.2},
    },
    )


@pytest.mark.django_db
class TestViewOrders:
    def test_admin_sees_all_orders_with_status_and_fulfillment_method(
            self, admin_client, guest_order, another_guest_order):
        response = admin_client.get('/store-admin/orders/')

        assert response.status_code == status.HTTP_200_OK
        order_ids = {o['id'] for o in response.data}
        assert order_ids == {guest_order.id, another_guest_order.id}

        seen = {o['id']: o for o in response.data}
        assert seen[guest_order.id]['fulfillment_method'] == Order.FULFILLMENT_PICKUP
        assert seen[guest_order.id]['status'] == Order.STATUS_CONFIRMED
        assert seen[guest_order.id]['payment_status'] == Order.PAYMENT_STATUS_COMPLETE
        assert 'items' in seen[guest_order.id]

    def test_anonymous_cannot_list_orders(self, guest_order):
        client = APIClient()
        response = client.get('/store-front/orders/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_non_staff_customer_only_sees_their_own_orders(self, guest_order, another_guest_order):
        from customers.models import Customer
        user = User.objects.create_user(
            password='pw', email='shopper@example.com')
        customer = Customer.objects.get(user=user)
        own_order = Order.objects.create(
            customer=customer, fulfillment_method=Order.FULFILLMENT_PICKUP)

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get('/store-front/orders/')

        assert response.status_code == status.HTTP_200_OK
        order_ids = {o['id'] for o in response.data}
        assert order_ids == {own_order.id}
