from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from djmoney.models.fields import MoneyField
from uuid import uuid4


class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True, related_name='carts')
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user'], condition=models.Q(user__isnull=False),
                name='unique_active_cart_per_user'),
        ]
        indexes = [
            models.Index(fields=['last_activity']),
        ]


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name='items')
    variant = models.ForeignKey('catalog.Variant', on_delete=models.CASCADE)
    quantity = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)]
    )
    # Snapshot of variant.unit_price at the moment this line was first
    # added — never touched again, including on quantity bumps. Lets
    # GET cart flag price_changed (cart transparency: Spring recalculates
    # each line on read; Django had no baseline to compare against).
    price_at_add = MoneyField(
        max_digits=6, decimal_places=2, default_currency='USD',
        null=True, blank=True)

    class Meta:
        unique_together = [['cart', 'variant']]
