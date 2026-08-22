from django.db import models
from djmoney.models.fields import MoneyField


class Shipment(models.Model):
    """A single booked delivery for one order, via a shipping provider
    (shipping/gateways/ — Dawurobo today).

    One-to-one with Order, unlike Payment's ForeignKey: an order gets
    exactly one active booking (a failed booking is retried in place,
    via `booking_failed`, not stacked as a new row) rather than one row
    per attempt.
    """
    STATUS_PENDING = 'PENDING'
    STATUS_BOOKED = 'BOOKED'
    STATUS_DISPATCHED = 'DISPATCHED'
    STATUS_OUT_FOR_DELIVERY = 'OUT_FOR_DELIVERY'
    STATUS_DELIVERED = 'DELIVERED'
    STATUS_DELIVERY_FAILED = 'DELIVERY_FAILED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_BOOKED, 'Booked'),
        (STATUS_DISPATCHED, 'Dispatched'),
        (STATUS_OUT_FOR_DELIVERY, 'Out for Delivery'),
        (STATUS_DELIVERED, 'Delivered'),
        (STATUS_DELIVERY_FAILED, 'Delivery Failed'),
    ]
    # Forward-only progression (data-model.md's transition table) — a
    # webhook event moving `status` backward, or repeating the current
    # value, is a no-op (research.md §4, FR-007).
    _STATUS_ORDER = [
        STATUS_PENDING, STATUS_BOOKED, STATUS_DISPATCHED,
        STATUS_OUT_FOR_DELIVERY, STATUS_DELIVERED,
    ]

    PROVIDER_DAWUROBO = 'DAWUROBO'
    PROVIDER_CHOICES = [
        (PROVIDER_DAWUROBO, 'Dawurobo'),
    ]

    order = models.OneToOneField(
        'orders.Order', on_delete=models.PROTECT, related_name='shipment')
    provider = models.CharField(
        max_length=20, choices=PROVIDER_CHOICES, default=PROVIDER_DAWUROBO)
    # The provider's shipment/tracking id. Set once booking succeeds.
    tracking_reference = models.CharField(max_length=100, unique=True, null=True, blank=True)
    carrier_name = models.CharField(max_length=100, blank=True, default='')
    cost = MoneyField(max_digits=10, decimal_places=2, default_currency='GHS', default=0)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    # Set when the provider rejects/can't complete a booking attempt
    # (FR-010) — surfaced to staff instead of leaving the order stuck
    # silently.
    booking_failed = models.BooleanField(default=False)
    estimated_delivery_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order']),
            models.Index(fields=['status']),
        ]

    def status_rank(self):
        try:
            return self._STATUS_ORDER.index(self.status)
        except ValueError:
            return -1  # e.g. DELIVERY_FAILED — a side branch, not on the happy path
