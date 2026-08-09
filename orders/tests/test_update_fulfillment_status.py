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
class TestUpdateFulfillmentStatus:
    def test_admin_marks_pickup_order_ready_for_pickup(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_PICKUP)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_READY_FOR_PICKUP})

        assert response.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.status == Order.STATUS_READY_FOR_PICKUP

    def test_admin_marks_delivery_order_out_for_delivery(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_DELIVERY)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_OUT_FOR_DELIVERY})

        assert response.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.status == Order.STATUS_OUT_FOR_DELIVERY

    def test_cannot_mark_delivery_order_ready_for_pickup(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_DELIVERY)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_READY_FOR_PICKUP})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        order.refresh_from_db()
        assert order.status == Order.STATUS_CONFIRMED

    def test_cannot_mark_pickup_order_out_for_delivery(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_PICKUP)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_OUT_FOR_DELIVERY})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_fulfill_an_unpaid_order(self, admin_client, make_order):
        order = make_order(
            Order.FULFILLMENT_PICKUP,
            payment_status=Order.PAYMENT_STATUS_PENDING, order_status='')

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_READY_FOR_PICKUP})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_move_status_backward(self, admin_client, make_order):
        order = make_order(
            Order.FULFILLMENT_PICKUP, order_status=Order.STATUS_COMPLETED)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_READY_FOR_PICKUP})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_admin_cannot_update_fulfillment_status(self, make_order):
        order = make_order(Order.FULFILLMENT_PICKUP)
        client = APIClient()

        response = client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_READY_FOR_PICKUP})

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
