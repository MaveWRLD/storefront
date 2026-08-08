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

    placed_at = models.DateTimeField(auto_now_add=True)
    payment_status = models.CharField(
        max_length=1, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_STATUS_PENDING)
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
