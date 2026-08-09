from .models import Notification


def notify(order, event_type, message):
    """Record a customer notification for an order milestone.

    Business Rule (Notifications): 'Customer notified at every
    status-changing milestone'. Adapted from Saleor's manager.notify()
    (core/notify.py): callers fire an event, the delivery channel is
    decoupled — no email/SMS provider is wired up yet, so this only
    persists the record for now.
    """
    return Notification.objects.create(
        order=order,
        event_type=event_type,
        recipient=order.get_email(),
        message=message,
    )
