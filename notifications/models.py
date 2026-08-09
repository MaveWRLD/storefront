from django.db import models


class Notification(models.Model):
    """A record of a customer notification sent for an order milestone.

    Business Rule (Notifications): 'Customer notified at every
    status-changing milestone'. No email/SMS provider is wired up yet (that
    infra doesn't exist in this codebase) — adapted from Saleor's
    manager.notify() pattern (core/notify.py): the event is always recorded
    here, decoupled from which channel eventually delivers it.
    """
    EVENT_ORDER_CONFIRMED = 'ORDER_CONFIRMED'
    EVENT_READY_FOR_PICKUP = 'READY_FOR_PICKUP'
    EVENT_OUT_FOR_DELIVERY = 'OUT_FOR_DELIVERY'
    EVENT_DELIVERED = 'DELIVERED'
    EVENT_REFUND_DECISION = 'REFUND_DECISION'
    EVENT_CHOICES = [
        (EVENT_ORDER_CONFIRMED, 'Order Confirmed'),
        (EVENT_READY_FOR_PICKUP, 'Ready for Pickup'),
        (EVENT_OUT_FOR_DELIVERY, 'Out for Delivery'),
        (EVENT_DELIVERED, 'Delivered'),
        (EVENT_REFUND_DECISION, 'Refund Decision'),
    ]

    order = models.ForeignKey(
        'orders.Order', on_delete=models.CASCADE, related_name='notifications')
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    recipient = models.CharField(max_length=255)
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sent_at']
