from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from catalog.models import Collection, Product, Variant
from orders.models import Order, OrderItem
from payment.models import Payment


@pytest.fixture
def order():
    return Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_PICKUP,
        guest_name='Guest', guest_email='guest@example.com',
        guest_phone='0800000000',
    )


@pytest.fixture
def variant():
    product = Product.objects.create(
        title='Test Shirt', slug='test-shirt',
        collection=Collection.objects.create(title='Shirts'))
    # allocated=2 simulates the checkout-time allocation (US-30) this
    # abandoned payment held onto.
    return Variant.objects.create(
        product=product, sku='test-shirt', unit_price=1000,
        inventory=5, allocated=2)


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

    def test_expiring_a_stale_payment_releases_the_orders_allocated_stock(self, order, variant):
        """US-34: checkout (US-30) only ever holds stock in `allocated` —
        Business Rule (Warehouse): 'Stock decrements only on payment
        success, not at checkout' — so an abandoned payment must release
        that allocation, or the stock is held forever with no path back to
        available-to-sell."""
        OrderItem.objects.create(
            order=order, variant=variant, quantity=2, unit_price=variant.unit_price)
        stale = Payment.objects.create(
            order=order, reference='ref-stale', amount=1000)
        Payment.objects.filter(pk=stale.pk).update(
            modified_at=timezone.now() - timedelta(hours=2))

        call_command('expire_abandoned_payments')

        stale.refresh_from_db()
        variant.refresh_from_db()
        assert stale.status == Payment.STATUS_FAILED
        assert variant.allocated == 0
        assert variant.inventory == 5

    def test_recent_pending_payment_does_not_release_allocated(self, order, variant):
        OrderItem.objects.create(
            order=order, variant=variant, quantity=2, unit_price=variant.unit_price)
        fresh = Payment.objects.create(
            order=order, reference='ref-fresh-alloc', amount=1000)
        Payment.objects.filter(pk=fresh.pk).update(
            modified_at=timezone.now() - timedelta(minutes=30))

        call_command('expire_abandoned_payments')

        variant.refresh_from_db()
        assert variant.allocated == 2

    def test_untracked_variant_allocation_is_left_alone(self, order, variant):
        Variant.objects.filter(pk=variant.pk).update(track_inventory=False)
        OrderItem.objects.create(
            order=order, variant=variant, quantity=2, unit_price=variant.unit_price)
        stale = Payment.objects.create(
            order=order, reference='ref-stale-untracked', amount=1000)
        Payment.objects.filter(pk=stale.pk).update(
            modified_at=timezone.now() - timedelta(hours=2))

        call_command('expire_abandoned_payments')

        variant.refresh_from_db()
        assert variant.allocated == 2
