from django.db import models
from djmoney.models.fields import MoneyField


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

    STATUS_CONFIRMED = 'CONFIRMED'
    STATUS_FULFILLMENT = 'FULFILLMENT'
    STATUS_READY_FOR_PICKUP = 'READY_FOR_PICKUP'
    STATUS_OUT_FOR_DELIVERY = 'OUT_FOR_DELIVERY'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_DELIVERY_FAILED = 'DELIVERY_FAILED'
    STATUS_PENDING_RESOLUTION = 'PENDING_RESOLUTION'
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
    fulfillment_method = models.CharField(
        max_length=8, choices=FULFILLMENT_METHOD_CHOICES)
    customer = models.ForeignKey(
        'customers.Customer', on_delete=models.PROTECT, null=True, blank=True)
    subtotal = MoneyField(
        max_digits=10, decimal_places=2, default_currency='USD',
        default=0)
    # Set from the shipping rate quote selected at checkout (shipping app,
    # 004-shipping-integration). Stays 0 for pickup-method orders.
    shipping_cost = MoneyField(
        max_digits=10, decimal_places=2, default_currency='USD',
        default=0)
    # The recipient contact + delivery address, persisted so booking
    # (shipping/services.py:book_shipment_for_order) can re-send it once
    # payment succeeds — Dawurobo re-prices at booking time rather than
    # accepting a quote token, so there's nothing else to carry through
    # but the address itself (shipping/serializers.py:AddressSerializer
    # shape: recipient_name, email, phone, street_address, city, region,
    # ghana_post_gps, coordinates).
    #
    # Also doubles as the ONLY guest-identity record on the order — there
    # is no separate name/email/phone field. An authenticated customer's
    # PICKUP order can leave this null (the account is the identity); a
    # guest order of either fulfillment method cannot, since nothing else
    # on Order identifies who placed it.
    shipping_address = models.JSONField(null=True, blank=True)

    def get_email(self):
        if self.shipping_address and self.shipping_address.get('email'):
            return self.shipping_address['email']
        if self.customer_id:
            return self.customer.user.email
        return ''

    def get_total(self):
        return self.subtotal + self.shipping_cost

    class Meta:
        permissions = [
            ('cancel_order', 'Can cancel order')
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(customer__isnull=False)
                    | models.Q(shipping_address__isnull=False)
                ),
                name='order_has_customer_or_guest_contact',
            )
        ]
        indexes = [
            models.Index(fields=['customer', '-placed_at']),
            models.Index(fields=['status']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['fulfillment_method']),
        ]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='items')
    variant = models.ForeignKey(
        'catalog.Variant', on_delete=models.PROTECT, related_name='orderitems')
    quantity = models.PositiveSmallIntegerField()
    unit_price = MoneyField(max_digits=6, decimal_places=2, default_currency='USD')
