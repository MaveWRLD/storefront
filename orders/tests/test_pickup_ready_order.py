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
def make_order():
    def _make(fulfillment_method, payment_status=Order.PAYMENT_STATUS_COMPLETE,
              order_status=Order.STATUS_CONFIRMED):
        return Order.objects.create(
            fulfillment_method=fulfillment_method,
            payment_status=payment_status,
            status=order_status,
            guest_name='Guest',
            guest_email='guest@example.com',
            guest_phone='0800000000',
        )
    return _make


@pytest.mark.django_db
class TestPickupReadyOrder:
    """US-14: Business Rule (Shipping) 'No fixed pickup window — Admin
    decides case by case' — no timer/scheduled task moves an order into
    pending resolution; it's always an explicit admin action."""

    def test_admin_flags_uncollected_pickup_as_pending_resolution(self, admin_client, make_order):
        order = make_order(
            Order.FULFILLMENT_PICKUP, order_status=Order.STATUS_READY_FOR_PICKUP)

        response = admin_client.patch(
            f'/store/orders/{order.id}/',
            {'status': Order.STATUS_PENDING_RESOLUTION})

        assert response.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.status == Order.STATUS_PENDING_RESOLUTION

    def test_cannot_flag_pending_resolution_before_ready_for_pickup(self, admin_client, make_order):
        order = make_order(
            Order.FULFILLMENT_PICKUP, order_status=Order.STATUS_CONFIRMED)

        response = admin_client.patch(
            f'/store/orders/{order.id}/',
            {'status': Order.STATUS_PENDING_RESOLUTION})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_flag_delivery_order_as_pending_resolution(self, admin_client, make_order):
        order = make_order(
            Order.FULFILLMENT_DELIVERY, order_status=Order.STATUS_OUT_FOR_DELIVERY)

        response = admin_client.patch(
            f'/store/orders/{order.id}/',
            {'status': Order.STATUS_PENDING_RESOLUTION})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_customer_collects_after_pending_resolution_completes_order(self, admin_client, make_order):
        order = make_order(
            Order.FULFILLMENT_PICKUP, order_status=Order.STATUS_PENDING_RESOLUTION)

        response = admin_client.patch(
            f'/store/orders/{order.id}/', {'status': Order.STATUS_COMPLETED})

        assert response.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.status == Order.STATUS_COMPLETED

    def test_pending_resolution_cannot_go_back_to_ready_for_pickup(self, admin_client, make_order):
        order = make_order(
            Order.FULFILLMENT_PICKUP, order_status=Order.STATUS_PENDING_RESOLUTION)

        response = admin_client.patch(
            f'/store/orders/{order.id}/',
            {'status': Order.STATUS_READY_FOR_PICKUP})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
