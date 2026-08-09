from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from orders.models import Order
from payment.models import Payment


@pytest.fixture
def order():
    return Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_PICKUP,
        guest_name='Guest', guest_email='guest@example.com',
        guest_phone='0800000000',
    )


@pytest.mark.django_db
class TestPaymentSessionExpiry:
    """Business Rule (Checkout): 'Checkout/payment session expiry' — payment
    abandonAfter 1 hour. Adapted from cart's expire_abandoned_carts
    (management command run on a schedule), same shape, different TTL/model."""

    def test_stale_pending_payment_is_marked_failed(self, order):
        stale = Payment.objects.create(
            order=order, reference='ref-stale', amount=1000)
        Payment.objects.filter(pk=stale.pk).update(
            modified_at=timezone.now() - timedelta(hours=2))

        call_command('expire_abandoned_payments')

        stale.refresh_from_db()
        assert stale.status == Payment.STATUS_FAILED

    def test_recent_pending_payment_is_left_alone(self, order):
        fresh = Payment.objects.create(
            order=order, reference='ref-fresh', amount=1000)
        Payment.objects.filter(pk=fresh.pk).update(
            modified_at=timezone.now() - timedelta(minutes=30))

        call_command('expire_abandoned_payments')

        fresh.refresh_from_db()
        assert fresh.status == Payment.STATUS_PENDING

    def test_already_successful_payment_is_untouched(self, order):
        succeeded = Payment.objects.create(
            order=order, reference='ref-ok', amount=1000, status=Payment.STATUS_SUCCESS)
        Payment.objects.filter(pk=succeeded.pk).update(
            modified_at=timezone.now() - timedelta(hours=2))

        call_command('expire_abandoned_payments')

        succeeded.refresh_from_db()
        assert succeeded.status == Payment.STATUS_SUCCESS
