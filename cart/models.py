from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
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

    class Meta:
        unique_together = [['cart', 'variant']]
