from django.db import models
from djmoney.models.fields import MoneyField


class Payment(models.Model):
    """A single payment attempt against an order, via Paystack.

    Adapted from Saleor's Payment model, scaled down hard: single gateway
    (no `gateway` field needed), no billing-address snapshot, no card
    fields (Paystack hosts its own checkout page, we never see card data).
    Several attempts can exist per order (each failed attempt keeps its
    own row) so retrying (US-11) doesn't need any extra machinery.
    """
    STATUS_PENDING = 'PENDING'
    STATUS_SUCCESS = 'SUCCESS'
    STATUS_FAILED = 'FAILED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    order = models.ForeignKey(
        'orders.Order', on_delete=models.PROTECT, related_name='payments')
    # Our own idempotency key, sent to Paystack as its transaction reference.
    reference = models.CharField(max_length=100, unique=True)
    amount = MoneyField(max_digits=10, decimal_places=2, default_currency='USD')
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
