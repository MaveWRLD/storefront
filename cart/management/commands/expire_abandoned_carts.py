from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from cart.models import Cart


class Command(BaseCommand):
    """Delete carts inactive past CART_ABANDONMENT_TTL_DAYS.

    Adapted from Saleor's delete_expired_checkouts task
    (saleor/checkout/tasks.py), simplified to a single flat TTL measured off
    Cart.last_activity — run this on a schedule (cron/celery beat), not
    on every request, matching Saleor's periodic-sweep pattern.
    """
    help = 'Delete carts with no activity for CART_ABANDONMENT_TTL_DAYS.'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(
            days=settings.CART_ABANDONMENT_TTL_DAYS)
        deleted_count, _ = Cart.objects.filter(
            last_activity__lt=cutoff).delete()
        self.stdout.write(f'Deleted {deleted_count} abandoned cart(s).')
