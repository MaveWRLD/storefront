from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Variant
from customers.models import Customer
from orders.models import Order, OrderItem
from shipping.gateways import ShippingProviderError
from shipping.models import Shipment

User = get_user_model()
ADDRESS = {
    'recipient_name': 'Guest', 'email': 'guest@example.com', 'phone': '0800000000',
    'street_address': '12 Example Rd', 'city': 'Accra', 'region': 'Greater Accra',
    'coordinates': {'lat': 5.6037, 'lng': -0.1870},
}
BOOKING_RESULT = {'tracking_reference': 'DWB-789', 'estimated_delivery_at': '2026-08-22T00:00:00Z'}


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
        product=product, sku='test-shirt', unit_price=1000, inventory=5, allocated=1)


@pytest.fixture
def make_order(variant):
    def _make(fulfillment_method=Order.FULFILLMENT_DELIVERY,
              payment_status=Order.PAYMENT_STATUS_COMPLETE,
              order_status=Order.STATUS_CONFIRMED, shipping_address=ADDRESS):
        # No shipping_address and no guest identity would violate
        # order_has_customer_or_guest_contact — an order missing its
        # quote still needs *some* identity, so fall back to a customer
        # when a test explicitly wants shipping_address=None.
        customer = None
        if shipping_address is None:
            # Customer is auto-created by a post_save signal on User —
            # creating one directly here would collide with it.
            user = User.objects.create_user(
                email=f'shopper-{User.objects.count()}@example.com', password='x')
            customer = Customer.objects.get(user=user)
        order = Order.objects.create(
            customer=customer,
            fulfillment_method=fulfillment_method, payment_status=payment_status,
            status=order_status, shipping_address=shipping_address)
        OrderItem.objects.create(order=order, variant=variant, quantity=1, unit_price=variant.unit_price)
        return order
    return _make


def pickup_url(order_id):
    return f'/store-admin/shipments/{order_id}/pickup/'


@pytest.mark.django_db
class TestCreatePickupAdmin:
    """Staff-triggered booking: customer pays -> Order.status=CONFIRMED
    -> staff packages -> staff calls this endpoint -> Dawurobo books the
    pickup. Not automatic on payment (see payment/serializers.py)."""

    def test_staff_can_create_pickup_for_packaged_paid_order(self, admin_client, make_order):
        order = make_order()

        with patch('shipping.gateways.dawurobo.DawuroboGateway.create_shipment') as mocked:
            mocked.return_value = BOOKING_RESULT
            response = admin_client.post(pickup_url(order.id))

        assert response.status_code == status.HTTP_201_CREATED
        shipment = Shipment.objects.get(order=order)
        assert shipment.tracking_reference == 'DWB-789'
        assert shipment.status == Shipment.STATUS_BOOKED
        order.refresh_from_db()
        assert order.status == Order.STATUS_FULFILLMENT

    def test_non_staff_cannot_create_pickup(self, make_order):
        order = make_order()
        client = APIClient()
        client.force_authenticate(user=User(is_staff=False))

        response = client.post(pickup_url(order.id))

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not Shipment.objects.filter(order=order).exists()

    def test_pickup_order_is_rejected(self, admin_client, make_order):
        order = make_order(fulfillment_method=Order.FULFILLMENT_PICKUP, shipping_address=None)

        response = admin_client.post(pickup_url(order.id))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Shipment.objects.filter(order=order).exists()

    def test_unpaid_order_is_rejected(self, admin_client, make_order):
        order = make_order(payment_status=Order.PAYMENT_STATUS_PENDING, order_status='')

        response = admin_client.post(pickup_url(order.id))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Shipment.objects.filter(order=order).exists()

    def test_unpackaged_order_is_rejected(self, admin_client, make_order):
        order = make_order(order_status=Order.STATUS_FULFILLMENT)

        response = admin_client.post(pickup_url(order.id))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Shipment.objects.filter(order=order).exists()

    def test_order_with_no_quoted_address_is_rejected(self, admin_client, make_order):
        order = make_order(shipping_address=None)

        response = admin_client.post(pickup_url(order.id))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Shipment.objects.filter(order=order).exists()

    def test_creating_pickup_twice_conflicts(self, admin_client, make_order):
        order = make_order()
        with patch('shipping.gateways.dawurobo.DawuroboGateway.create_shipment') as mocked:
            mocked.return_value = BOOKING_RESULT
            admin_client.post(pickup_url(order.id))

        response = admin_client.post(pickup_url(order.id))

        assert response.status_code == status.HTTP_409_CONFLICT
        assert Shipment.objects.filter(order=order).count() == 1

    def test_booking_failure_flags_the_order(self, admin_client, make_order):
        order = make_order()

        with patch('shipping.gateways.dawurobo.DawuroboGateway.create_shipment') as mocked:
            mocked.side_effect = ShippingProviderError('Address rejected by courier.')
            response = admin_client.post(pickup_url(order.id))

        assert response.status_code == status.HTTP_201_CREATED
        shipment = Shipment.objects.get(order=order)
        assert shipment.booking_failed is True
        assert shipment.tracking_reference is None
