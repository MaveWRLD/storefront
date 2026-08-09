from django.conf import settings
from django.db import models
from djmoney.models.fields import MoneyField
from djmoney.money import Money


class Order(models.Model):
    PAYMENT_STATUS_PENDING = 'P'
    PAYMENT_STATUS_COMPLETE = 'C'
    PAYMENT_STATUS_FAILED = 'F'
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_STATUS_PENDING, 'Pending'),
        (PAYMENT_STATUS_COMPLETE, 'Complete'),
        (PAYMENT_STATUS_FAILED, 'Failed')
    ]

    FULFILLMENT_PICKUP = 'PICKUP'
    FULFILLMENT_DELIVERY = 'DELIVERY'
    FULFILLMENT_METHOD_CHOICES = [
        (FULFILLMENT_PICKUP, 'Pickup'),
        (FULFILLMENT_DELIVERY, 'Delivery'),
    ]

    # US-13 tracking stages. Mirrors Saleor's Order status progression plus
    # its Fulfillment sub-entity, collapsed onto Order itself since the
    # Fulfillment sub-entity (per the Domains page) isn't built yet.
    # READY_FOR_PICKUP/OUT_FOR_DELIVERY are mutually exclusive with each
    # other depending on fulfillment_method, matching that field's PICKUP/
    # DELIVERY split. Blank until payment succeeds (US-10 moves it to
    # CONFIRMED) — an unpaid order has no tracking stage yet. Transitions
    # from CONFIRMED onward are an admin action (US-24/US-14/US-15), not
    # built by this story.
    STATUS_CONFIRMED = 'CONFIRMED'
    STATUS_FULFILLMENT = 'FULFILLMENT'
    STATUS_READY_FOR_PICKUP = 'READY_FOR_PICKUP'
    STATUS_OUT_FOR_DELIVERY = 'OUT_FOR_DELIVERY'
    STATUS_COMPLETED = 'COMPLETED'
    # Business Rule (Shipping): 'Failed delivery triggers reschedule, not
    # auto-cancel' (US-15/US-24/US-25). A side-branch off OUT_FOR_DELIVERY,
    # not a step in the normal progression — the only way out of it is back
    # to OUT_FOR_DELIVERY (redispatch) or forward to COMPLETED once redelivered.
    STATUS_DELIVERY_FAILED = 'DELIVERY_FAILED'
    # Business Rule (Shipping): 'No fixed pickup window — Admin decides case
    # by case' (US-14). A side-branch off READY_FOR_PICKUP, mirroring
    # STATUS_DELIVERY_FAILED's shape: no scheduled task ever sets this, only
    # an explicit admin action, since there's no fixed window to expire against.
    STATUS_PENDING_RESOLUTION = 'PENDING_RESOLUTION'
    # Business Rule (Shipping): 'Failed delivery triggers reschedule, not
    # auto-cancel' (US-25) — the other half of that rule: if the admin gives
    # up rather than rescheduling/waiting, the order is cancelled and its
    # lines are returned to stock. A side-branch off DELIVERY_FAILED or
    # PENDING_RESOLUTION only, terminal (no further transitions out of it).
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_CHOICES = [
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_FULFILLMENT, 'Fulfillment'),
        (STATUS_READY_FOR_PICKUP, 'Ready for Pickup'),
        (STATUS_OUT_FOR_DELIVERY, 'Out for Delivery'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_DELIVERY_FAILED, 'Delivery Failed'),
        (STATUS_PENDING_RESOLUTION, 'Pending Resolution'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    placed_at = models.DateTimeField(auto_now_add=True)
    payment_status = models.CharField(
        max_length=1, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_STATUS_PENDING)
    status = models.CharField(
        max_length=19, choices=STATUS_CHOICES, blank=True, default='')
    # Saleor distinguishes delivery vs. click-and-collect via delivery_method
    # being a ShippingMethod or a Warehouse. Neither the Shipping-rate nor
    # Warehouse domain exists here yet, so this is scaled down to a plain,
    # required, mutually-exclusive tag — no cost/zone/warehouse config behind
    # it. Required (no default): an order can't exist without one, which is
    # what makes "payment can't proceed until it's chosen" true today.
    fulfillment_method = models.CharField(
        max_length=8, choices=FULFILLMENT_METHOD_CHOICES)
    # Adapted from Saleor's Order.user (nullable) + user_email: a registered
    # customer's order sets `customer`; a guest order leaves it null and
    # carries its own contact details instead.
    customer = models.ForeignKey(
        'customers.Customer', on_delete=models.PROTECT, null=True, blank=True)
    guest_name = models.CharField(max_length=255, blank=True, default='')
    guest_email = models.EmailField(blank=True, default='')
    guest_phone = models.CharField(max_length=32, blank=True, default='')

    def get_email(self):
        if self.customer_id:
            return self.customer.user.email
        return self.guest_email

    def get_total(self):
        return sum(
            (item.quantity * item.unit_price for item in self.items.all()),
            start=Money(0, settings.DEFAULT_CURRENCY)
        )

    class Meta:
        permissions = [
            ('cancel_order', 'Can cancel order')
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(customer__isnull=False)
                    | (~models.Q(guest_email='') & ~models.Q(guest_name=''))
                ),
                name='order_has_customer_or_guest_contact',
            )
        ]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='items')
    # Domains — Catalog class diagram: an order line buys a specific
    # Variant, not the whole product (price/stock live on Variant).
    variant = models.ForeignKey(
        'catalog.Variant', on_delete=models.PROTECT, related_name='orderitems')
    quantity = models.PositiveSmallIntegerField()
    unit_price = MoneyField(max_digits=6, decimal_places=2, default_currency='USD')
