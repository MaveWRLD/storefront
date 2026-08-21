import hashlib
import hmac
import json
from unittest.mock import patch

from django.conf import settings
from rest_framework.test import APIClient
from rest_framework import status
import pytest

from catalog.models import Collection, Product, Variant
from orders.models import Order, OrderItem
from payment.models import Payment

WEBHOOK_URL = '/store-front/payments/webhook/'


def sign(body_bytes):
    return hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode(), body_bytes, hashlib.sha512,
    ).hexdigest()


def post_webhook(payload, signature=None):
    body = json.dumps(payload).encode()
    headers = {}
    if signature is not None:
        headers['HTTP_X_PAYSTACK_SIGNATURE'] = signature
    client = APIClient()
    return client.post(
        WEBHOOK_URL, data=body, content_type='application/json', **headers)


def charge_success_payload(reference):
    return {'event': 'charge.success', 'data': {'reference': reference, 'status': 'success'}}


@pytest.fixture
def variant():
    product = Product.objects.create(
        title='Test Shirt', slug='test-shirt',
        collection=Collection.objects.create(title='Shirts'))
    return Variant.objects.create(
        product=product, sku='test-shirt', unit_price=1000,
        inventory=5, allocated=2)


@pytest.fixture
def order(variant):
    order = Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_DELIVERY,
        shipping_address={
        'recipient_name': 'Guest', 'email': 'guest@example.com',
        'phone': '0800000000', 'street_address': '1 Test St',
        'city': 'Accra', 'region': 'Greater Accra',
        'coordinates': {'lat': 5.6, 'lng': -0.2},
    },
    )
    OrderItem.objects.create(
        order=order, variant=variant, quantity=2, unit_price=variant.unit_price)
    return order


@pytest.fixture
def pending_payment(order):
    return Payment.objects.create(
        order=order, reference='webhook-ref-1', amount=order.get_total())


@pytest.mark.django_db
class TestPaystackWebhook:
    """P1: Paystack webhook is the source-of-truth reconciliation path,
    independent of the client-driven verify poll (US-10)."""

    def test_valid_signature_confirms_payment_and_decrements_stock(self, pending_payment, variant, order):
        payload = charge_success_payload(pending_payment.reference)
        body = json.dumps(payload).encode()

        response = post_webhook(payload, signature=sign(body))

        assert response.status_code == status.HTTP_200_OK
        pending_payment.refresh_from_db()
        variant.refresh_from_db()
        order.refresh_from_db()
        assert pending_payment.status == Payment.STATUS_SUCCESS
        assert variant.inventory == 3
        assert variant.allocated == 0
        assert order.payment_status == Order.PAYMENT_STATUS_COMPLETE
        assert order.status == Order.STATUS_CONFIRMED

    def test_invalid_signature_returns_400_and_makes_no_change(self, pending_payment, variant):
        payload = charge_success_payload(pending_payment.reference)

        response = post_webhook(payload, signature='not-a-real-signature')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        pending_payment.refresh_from_db()
        variant.refresh_from_db()
        assert pending_payment.status == Payment.STATUS_PENDING
        assert variant.inventory == 5
        assert variant.allocated == 2

    def test_missing_signature_header_returns_400(self, pending_payment):
        payload = charge_success_payload(pending_payment.reference)

        response = post_webhook(payload, signature=None)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        pending_payment.refresh_from_db()
        assert pending_payment.status == Payment.STATUS_PENDING

    def test_unknown_reference_returns_200_and_is_a_no_op(self):
        payload = charge_success_payload('no-such-reference')

        response = post_webhook(payload, signature=sign(json.dumps(payload).encode()))

        assert response.status_code == status.HTTP_200_OK

    def test_duplicate_webhook_after_success_does_not_double_decrement_stock(self, pending_payment, variant):
        payload = charge_success_payload(pending_payment.reference)
        body = json.dumps(payload).encode()
        signature = sign(body)
        post_webhook(payload, signature=signature)

        response = post_webhook(payload, signature=signature)

        assert response.status_code == status.HTTP_200_OK
        variant.refresh_from_db()
        assert variant.inventory == 3
        assert variant.allocated == 0

    def test_non_charge_success_event_is_ignored(self, pending_payment):
        payload = {'event': 'charge.failed', 'data': {'reference': pending_payment.reference}}

        response = post_webhook(payload, signature=sign(json.dumps(payload).encode()))

        assert response.status_code == status.HTTP_200_OK
        pending_payment.refresh_from_db()
        assert pending_payment.status == Payment.STATUS_PENDING
