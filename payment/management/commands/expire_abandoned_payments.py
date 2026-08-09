from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from payment.models import Payment


class Command(BaseCommand):
    """Mark PENDING payments as FAILED once PAYMENT_ABANDON_AFTER_MINUTES
    has passed with no verified outcome.

    Adapted from cart's expire_abandoned_carts — same run-on-a-schedule
    shape (cron/celery beat), different TTL/model. Business Rule (Checkout):
    'Checkout/payment session expiry' — payment abandonAfter 1 hour.
    """
    help = 'Mark stale PENDING payments as FAILED past PAYMENT_ABANDON_AFTER_MINUTES.'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(
            minutes=settings.PAYMENT_ABANDON_AFTER_MINUTES)
        updated_count = Payment.objects.filter(
            status=Payment.STATUS_PENDING, modified_at__lt=cutoff
        ).update(status=Payment.STATUS_FAILED)
        self.stdout.write(f'Expired {updated_count} abandoned payment(s).')
