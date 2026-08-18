from django.core.validators import MinValueValidator
from django.db import models
from uuid import uuid4


class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    # Business Rule (Checkout): 'Abandoned checkout preserves the cart' —
    # bumped on every save (item add/update/remove) so the TTL sweep in
    # expire_abandoned_carts measures inactivity, not age. Adapted from
    # Saleor's Checkout.last_change (checkout/models.py).
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['last_activity']),
        ]


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name='items')
    # Domains — Catalog class diagram: price/stock live on Variant, so a
    # cart line adds a specific variant, not the whole product.
    variant = models.ForeignKey('catalog.Variant', on_delete=models.CASCADE)
    quantity = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)]
    )

    class Meta:
        unique_together = [['cart', 'variant']]
