from django.db import models
from djmoney.models.fields import MoneyField


class Payment(models.Model):
    """A single payment attempt against an order, via a payment gateway
    (payment/gateways/ — Paystack today).

    Adapted from Saleor's Payment model, scaled down: no billing-address
    snapshot, no card fields (Paystack hosts its own checkout page, we
    never see card data). Several attempts can exist per order (each
    failed attempt keeps its own row) so retrying (US-11) doesn't need
    any extra machinery.
    """
    STATUS_PENDING = 'PENDING'
    STATUS_SUCCESS = 'SUCCESS'
    STATUS_FAILED = 'FAILED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    GATEWAY_PAYSTACK = 'PAYSTACK'
    GATEWAY_CHOICES = [
        (GATEWAY_PAYSTACK, 'Paystack'),
    ]

    order = models.ForeignKey(
        'orders.Order', on_delete=models.PROTECT, related_name='payments')
    # Our own idempotency key, sent to the gateway as its transaction reference.
    reference = models.CharField(max_length=100, unique=True)
    amount = MoneyField(max_digits=10, decimal_places=2, default_currency='USD')
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    # Which gateway implementation (payment/gateways/) this reference
    # belongs to — resolved via get_gateway() wherever a payment needs
    # to talk back to its gateway (verify, refund, webhook signature).
    gateway = models.CharField(
        max_length=20, choices=GATEWAY_CHOICES, default=GATEWAY_PAYSTACK)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', '-created_at']),
            models.Index(fields=['status']),
        ]
