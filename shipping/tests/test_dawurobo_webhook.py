import json
from unittest.mock import patch

from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Variant
from notifications.models import Notification
from orders.models import Order, OrderItem
from shipping.models import Shipment

WEBHOOK_URL = '/store-front/shipping/webhook/'


def post_webhook(payload, signature='valid-signature'):
    body = json.dumps(payload).encode()
    headers = {}
    if signature is not None:
        headers['HTTP_X_WEBHOOK_SIGNATURE'] = signature
    client = APIClient()
    return client.post(WEBHOOK_URL, data=body, content_type='application/json', **headers)


@pytest.fixture
def variant():
    product = Product.objects.create(
        title='Test Shirt', slug='test-shirt',
        collection=Collection.objects.create(title='Shirts'))
    return Variant.objects.create(product=product, sku='test-shirt', unit_price=1000, inventory=5)


@pytest.fixture
def order(variant):
    order = Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_DELIVERY,
        payment_status=Order.PAYMENT_STATUS_COMPLETE,
        status=Order.STATUS_FULFILLMENT,
        shipping_address={'recipient_name': 'Guest', 'email': 'guest@example.com', 'phone': '0800000000', 'street_address': '1 Test St', 'city': 'Accra', 'region': 'Greater Accra', 'coordinates': {'lat': 5.6, 'lng': -0.2}})
    OrderItem.objects.create(order=order, variant=variant, quantity=1, unit_price=variant.unit_price)
    return order


@pytest.fixture
def booked_shipment(order):
    return Shipment.objects.create(
        order=order, tracking_reference='sb_track_789',
        carrier_name='GIG Logistics', status=Shipment.STATUS_BOOKED)


def signature_ok(*args, **kwargs):
    return True


@pytest.mark.django_db
class TestDawuroboWebhook:
    """FR-006/FR-007/FR-008/FR-009: verified, idempotent status
    updates drive the order forward and notify the customer once."""

    def test_valid_event_advances_shipment_and_order_status(self, booked_shipment, order):
        with patch('shipping.gateways.dawurobo.DawuroboGateway.verify_webhook_signature', signature_ok):
            response = post_webhook(
                {'event': 'delivery.status_updated', 'data': {'tracking_reference': 'sb_track_789', 'status': 'out_for_delivery'}})

        assert response.status_code == status.HTTP_200_OK
        booked_shipment.refresh_from_db()
        order.refresh_from_db()
        assert booked_shipment.status == Shipment.STATUS_OUT_FOR_DELIVERY
        assert order.status == Order.STATUS_OUT_FOR_DELIVERY
        assert Notification.objects.filter(
            order=order, event_type=Notification.EVENT_OUT_FOR_DELIVERY).count() == 1

    def test_invalid_signature_returns_400_and_makes_no_change(self, booked_shipment):
        response = post_webhook(
            {'event': 'delivery.status_updated', 'data': {'tracking_reference': 'sb_track_789', 'status': 'out_for_delivery'}},
            signature='not-real')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        booked_shipment.refresh_from_db()
        assert booked_shipment.status == Shipment.STATUS_BOOKED

    def test_missing_signature_returns_400(self, booked_shipment):
        response = post_webhook(
            {'event': 'delivery.status_updated', 'data': {'tracking_reference': 'sb_track_789', 'status': 'out_for_delivery'}},
            signature=None)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unknown_tracking_reference_returns_200_and_is_a_no_op(self):
        with patch('shipping.gateways.dawurobo.DawuroboGateway.verify_webhook_signature', signature_ok):
            response = post_webhook({'event': 'delivery.status_updated', 'data': {'tracking_reference': 'no-such-ref', 'status': 'delivered'}})

        assert response.status_code == status.HTTP_200_OK

    def test_duplicate_event_does_not_double_notify(self, booked_shipment, order):
        with patch('shipping.gateways.dawurobo.DawuroboGateway.verify_webhook_signature', signature_ok):
            post_webhook({'event': 'delivery.status_updated', 'data': {'tracking_reference': 'sb_track_789', 'status': 'out_for_delivery'}})
            response = post_webhook({'event': 'delivery.status_updated', 'data': {'tracking_reference': 'sb_track_789', 'status': 'out_for_delivery'}})

        assert response.status_code == status.HTTP_200_OK
        assert Notification.objects.filter(
            order=order, event_type=Notification.EVENT_OUT_FOR_DELIVERY).count() == 1

    def test_out_of_order_event_does_not_move_status_backward(self, order):
        shipment = Shipment.objects.create(
            order=order, tracking_reference='sb_track_999', status=Shipment.STATUS_DELIVERED)
        with patch('shipping.gateways.dawurobo.DawuroboGateway.verify_webhook_signature', signature_ok):
            response = post_webhook({'event': 'delivery.status_updated', 'data': {'tracking_reference': 'sb_track_999', 'status': 'dispatched'}})

        assert response.status_code == status.HTTP_200_OK
        shipment.refresh_from_db()
        assert shipment.status == Shipment.STATUS_DELIVERED
