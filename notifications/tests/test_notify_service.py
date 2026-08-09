import pytest

from notifications.models import Notification
from notifications.services import notify
from orders.models import Order


@pytest.fixture
def order():
    return Order.objects.create(
        fulfillment_method=Order.FULFILLMENT_PICKUP,
        guest_name='Guest',
        guest_email='guest@example.com',
        guest_phone='0800000000',
    )


@pytest.mark.django_db
class TestNotifyService:
    def test_notify_creates_a_notification_record_for_the_order_recipient(self, order):
        notify(order, Notification.EVENT_ORDER_CONFIRMED, 'Your order is confirmed.')

        notification = Notification.objects.get(order=order)
        assert notification.event_type == Notification.EVENT_ORDER_CONFIRMED
        assert notification.recipient == 'guest@example.com'
        assert notification.message == 'Your order is confirmed.'
