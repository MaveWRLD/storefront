from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models, transaction
from django.utils import timezone

from catalog.models import Variant
from payment.models import Payment


class Command(BaseCommand):
    """Mark PENDING payments as FAILED once PAYMENT_ABANDON_AFTER_MINUTES
    has passed with no verified outcome.

    Adapted from cart's expire_abandoned_carts — same run-on-a-schedule
    shape (cron/celery beat), different TTL/model. Business Rule (Checkout):
    'Checkout/payment session expiry' — payment abandonAfter 1 hour.

    Business Rule (Warehouse): 'Stock decrements only on payment success,
    not at checkout' (US-34) — an abandoned order's stock was only ever
    held in `Variant.allocated` (checkout never touches `inventory`), so
    expiring the payment must also release that allocation, or the stock
    stays held forever with no path back to available-to-sell.
    """
    help = 'Mark stale PENDING payments as FAILED past PAYMENT_ABANDON_AFTER_MINUTES.'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(
            minutes=settings.PAYMENT_ABANDON_AFTER_MINUTES)
        stale_payments = Payment.objects.select_related('order').filter(
            status=Payment.STATUS_PENDING, modified_at__lt=cutoff)

        updated_count = 0
        for payment in stale_payments:
            with transaction.atomic():
                order_items = list(payment.order.items.select_related('variant'))
                locked_variants = {
                    v.pk: v for v in Variant.objects.select_for_update().filter(
                        pk__in=[item.variant_id for item in order_items]
                    ).order_by('pk')
                }
                for item in order_items:
                    variant = locked_variants[item.variant_id]
                    if variant.track_inventory:
                        Variant.objects.filter(pk=variant.pk).update(
                            allocated=models.F('allocated') - item.quantity)

                Payment.objects.filter(pk=payment.pk).update(
                    status=Payment.STATUS_FAILED)
                updated_count += 1

        self.stdout.write(f'Expired {updated_count} abandoned payment(s).')
