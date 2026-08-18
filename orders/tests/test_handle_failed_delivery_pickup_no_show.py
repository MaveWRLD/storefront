from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Variant
from orders.models import Order, OrderItem
from orders.serializers import UpdateOrderSerializer

User = get_user_model()


@pytest.fixture
def admin_client():
    client = APIClient()
    client.force_authenticate(user=User(is_staff=True))
    return client


@pytest.fixture
def variant():
    product = Product.objects.create(
        title='Test Shirt', slug='test-shirt',
        collection=Collection.objects.create(title='Shirts'))
    return Variant.objects.create(
        product=product, sku='test-shirt', unit_price=1000, inventory=0)


@pytest.fixture
def make_order(variant):
    def _make(fulfillment_method, order_status, quantity=2):
        order = Order.objects.create(
            fulfillment_method=fulfillment_method,
            payment_status=Order.PAYMENT_STATUS_COMPLETE,
            status=order_status,
            guest_name='Guest',
            guest_email='guest@example.com',
            guest_phone='0800000000',
        )
        OrderItem.objects.create(
            order=order, variant=variant, quantity=quantity,
            unit_price=variant.unit_price)
        return order
    return _make


@pytest.mark.django_db
class TestHandleFailedDeliveryPickupNoShow:
    """US-25: 'reschedule the attempt Or return the item to inventory if
    unresolved.' Reschedule already exists (DELIVERY_FAILED<->OUT_FOR_DELIVERY,
    US-15); this story adds the give-up-and-restock path, now that
    Variant.inventory exists as the Warehouse stand-in."""

    def test_giving_up_on_failed_delivery_cancels_and_restocks(self, admin_client, make_order, variant):
        order = make_order(Order.FULFILLMENT_DELIVERY, Order.STATUS_DELIVERY_FAILED, quantity=2)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_CANCELLED})

        assert response.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.status == Order.STATUS_CANCELLED
        variant.refresh_from_db()
        assert variant.inventory == 2

    def test_giving_up_on_pickup_no_show_cancels_and_restocks(self, admin_client, make_order, variant):
        order = make_order(Order.FULFILLMENT_PICKUP, Order.STATUS_PENDING_RESOLUTION, quantity=3)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_CANCELLED})

        assert response.status_code == status.HTTP_200_OK
        order.refresh_from_db()
        assert order.status == Order.STATUS_CANCELLED
        variant.refresh_from_db()
        assert variant.inventory == 3

    def test_cancelled_order_restocks_each_line_once(self, admin_client, make_order, variant):
        order = make_order(Order.FULFILLMENT_DELIVERY, Order.STATUS_DELIVERY_FAILED, quantity=1)

        admin_client.patch(f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_CANCELLED})

        variant.refresh_from_db()
        assert variant.inventory == 1

    def test_cannot_cancel_an_order_that_is_not_flagged(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_DELIVERY, Order.STATUS_OUT_FOR_DELIVERY)

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_CANCELLED})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cancelled_order_cannot_transition_further(self, admin_client, make_order):
        order = make_order(Order.FULFILLMENT_DELIVERY, Order.STATUS_DELIVERY_FAILED)
        admin_client.patch(f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_CANCELLED})

        response = admin_client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_OUT_FOR_DELIVERY})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_admin_cannot_cancel_order(self, make_order):
        order = make_order(Order.FULFILLMENT_DELIVERY, Order.STATUS_DELIVERY_FAILED)
        client = APIClient()

        response = client.patch(
            f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_CANCELLED})

        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_cancelling_a_paid_order_credits_inventory_not_allocated(self, admin_client, make_order, variant):
        """US-33: a paid order already had `inventory` decremented and
        `allocated` released at payment success (US-31) — cancelling it
        credits `inventory` back and leaves `allocated` alone."""
        order = make_order(Order.FULFILLMENT_DELIVERY, Order.STATUS_DELIVERY_FAILED, quantity=2)

        admin_client.patch(f'/store-admin/orders/{order.id}/', {'status': Order.STATUS_CANCELLED})

        variant.refresh_from_db()
        assert variant.inventory == 2
        assert variant.allocated == 0

    def test_cancelling_an_unpaid_order_releases_allocated_not_inventory(self, variant):
        """US-33: an order never paid for was only ever held in
        `allocated` (checkout, US-30, never touches `inventory`) — cancel
        must release `allocated` instead. `UpdateOrderSerializer.update()`
        is exercised directly since the only real endpoint
        (`OrderAdminViewSet`) requires `payment_status == COMPLETE` before
        any status transition, so this branch is unreachable through the
        API today but still needs to hold if that guard ever loosens."""
        Variant.objects.filter(pk=variant.pk).update(allocated=2)
        order = Order.objects.create(
            fulfillment_method=Order.FULFILLMENT_DELIVERY,
            payment_status=Order.PAYMENT_STATUS_PENDING,
            status=Order.STATUS_DELIVERY_FAILED,
            guest_name='Guest', guest_email='guest@example.com',
            guest_phone='0800000000',
        )
        OrderItem.objects.create(
            order=order, variant=variant, quantity=2, unit_price=variant.unit_price)

        UpdateOrderSerializer().update(order, {'status': Order.STATUS_CANCELLED})

        variant.refresh_from_db()
        assert variant.allocated == 0
        assert variant.inventory == 0
