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
    def _make(fulfillment_method, order_status):
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


@pytest.mark.django_db
class TestReceiveDeliveredOrder:
    def test_out_for_delivery_order_can_be_marked_delivered(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_DELIVERY, Order.STATUS_OUT_FOR_DELIVERY)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_COMPLETED})

        assert response.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.status == Order.STATUS_COMPLETED

    def test_failed_delivery_is_flagged_not_completed(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_DELIVERY, Order.STATUS_OUT_FOR_DELIVERY)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_DELIVERY_FAILED})

        assert response.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.status == Order.STATUS_DELIVERY_FAILED

    def test_failed_delivery_can_be_rescheduled_back_out(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_DELIVERY, Order.STATUS_DELIVERY_FAILED)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_OUT_FOR_DELIVERY})

        assert response.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.status == Order.STATUS_OUT_FOR_DELIVERY

    def test_failed_delivery_cannot_be_completed_directly(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_DELIVERY, Order.STATUS_DELIVERY_FAILED)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_COMPLETED})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        order.refresh_from_db()
        assert order.status == Order.STATUS_DELIVERY_FAILED

    def test_pickup_order_cannot_be_flagged_delivery_failed(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_PICKUP, Order.STATUS_READY_FOR_PICKUP)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_DELIVERY_FAILED})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_flag_delivery_failed_before_dispatch(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_DELIVERY, Order.STATUS_FULFILLMENT)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_DELIVERY_FAILED})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
