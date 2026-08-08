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

    placed_at = models.DateTimeField(auto_now_add=True)
    payment_status = models.CharField(
        max_length=1, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_STATUS_PENDING)
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
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.PROTECT, related_name='orderitems')
    quantity = models.PositiveSmallIntegerField()
    unit_price = MoneyField(max_digits=6, decimal_places=2, default_currency='USD')
