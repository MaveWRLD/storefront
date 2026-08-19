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
    guest_name = models.CharField(max_length=255, blank=True, default='')
    guest_email = models.EmailField(blank=True, default='')
    guest_phone = models.CharField(max_length=32, blank=True, default='')
    subtotal = MoneyField(
        max_digits=10, decimal_places=2, default_currency='USD',
        default=0)

    def get_email(self):
        if self.customer_id:
            return self.customer.user.email
        return self.guest_email

    def get_total(self):
        return self.subtotal

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
        indexes = [
            models.Index(fields=['customer', '-placed_at']),
            models.Index(fields=['status']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['fulfillment_method']),
            models.Index(fields=['guest_email']),
        ]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='items')
    variant = models.ForeignKey(
        'catalog.Variant', on_delete=models.PROTECT, related_name='orderitems')
    quantity = models.PositiveSmallIntegerField()
    unit_price = MoneyField(max_digits=6, decimal_places=2, default_currency='USD')
