"""Shipping-side business logic — the equivalent of
`payment/serializers.py`'s `confirm_payment()`: where booking and
status-transition logic lives, kept out of `views.py`.
"""
from django.db import transaction

from notifications.models import Notification
from notifications.services import notify
from orders.models import Order

from .gateways import ShippingProviderError, get_provider
from .models import Shipment

# Shipment.status -> Order.status (data-model.md's transition table).
# Only these four Order states are ever set from shipment updates; no
# new Order-level states are introduced (spec.md Assumptions).
_ORDER_STATUS_BY_SHIPMENT_STATUS = {
    Shipment.STATUS_PENDING: Order.STATUS_FULFILLMENT,
    Shipment.STATUS_BOOKED: Order.STATUS_FULFILLMENT,
    Shipment.STATUS_DISPATCHED: Order.STATUS_OUT_FOR_DELIVERY,
    Shipment.STATUS_OUT_FOR_DELIVERY: Order.STATUS_OUT_FOR_DELIVERY,
    Shipment.STATUS_DELIVERED: Order.STATUS_COMPLETED,
    Shipment.STATUS_DELIVERY_FAILED: Order.STATUS_DELIVERY_FAILED,
}

# Shipment.status -> the customer-facing milestone to notify on
# (FR-009). Booking states (PENDING/BOOKED) aren't customer-relevant
# milestones on their own.
_NOTIFICATION_EVENT_BY_SHIPMENT_STATUS = {
    Shipment.STATUS_DISPATCHED: (
        Notification.EVENT_SHIPMENT_DISPATCHED, 'Your order has been dispatched.'),
    Shipment.STATUS_OUT_FOR_DELIVERY: (
        Notification.EVENT_OUT_FOR_DELIVERY, 'Your order is out for delivery.'),
    Shipment.STATUS_DELIVERED: (
        Notification.EVENT_DELIVERED, 'Your order has been delivered.'),
    Shipment.STATUS_DELIVERY_FAILED: (
        Notification.EVENT_DELIVERY_FAILED, 'Delivery of your order failed.'),
}


# Dawurobo's confirmed webhook event names
# (docs.dawurobo.com/docs/webhooks: order.created, order.accepted,
# order.rejected, order.picked_up, order.in_transit, order.delivered,
# order.cancelled, order.rescheduled, order.returned, order.updated) and
# a handful of plausible bare-status aliases (the `data` object's own
# field names/values weren't documented) -> our internal
# Shipment.STATUS_* constants. `order.rescheduled`/`order.updated` have
# no clean mapping and are intentionally left out — an unrecognized
# status is a safe no-op (FR-007), not an error.
_PROVIDER_STATUS_ALIASES = {
    'order.created': Shipment.STATUS_PENDING,
    'order.accepted': Shipment.STATUS_BOOKED,
    'order.rejected': Shipment.STATUS_DELIVERY_FAILED,
    'order.picked_up': Shipment.STATUS_DISPATCHED,
    'order.in_transit': Shipment.STATUS_DISPATCHED,
    'order.delivered': Shipment.STATUS_DELIVERED,
    'order.cancelled': Shipment.STATUS_DELIVERY_FAILED,
    'order.returned': Shipment.STATUS_DELIVERY_FAILED,
    'pending': Shipment.STATUS_PENDING,
    'created': Shipment.STATUS_PENDING,
    'accepted': Shipment.STATUS_BOOKED,
    'booked': Shipment.STATUS_BOOKED,
    'picked_up': Shipment.STATUS_DISPATCHED,
    'dispatched': Shipment.STATUS_DISPATCHED,
    'in_transit': Shipment.STATUS_DISPATCHED,
    'out_for_delivery': Shipment.STATUS_OUT_FOR_DELIVERY,
    'delivered': Shipment.STATUS_DELIVERED,
    'rejected': Shipment.STATUS_DELIVERY_FAILED,
    'cancelled': Shipment.STATUS_DELIVERY_FAILED,
    'returned': Shipment.STATUS_DELIVERY_FAILED,
    'delivery_failed': Shipment.STATUS_DELIVERY_FAILED,
    'failed': Shipment.STATUS_DELIVERY_FAILED,
}


def normalize_provider_status(raw_status):
    """Map a provider's raw webhook status/event string onto one of our
    `Shipment.STATUS_*` constants, or None if unrecognized."""
    if raw_status in dict(Shipment.STATUS_CHOICES):
        return raw_status  # already one of ours
    return _PROVIDER_STATUS_ALIASES.get(str(raw_status).lower())


def book_shipment_for_order(order):
    """Book a shipment for `order` with its quoted address (FR-004).
    Called from staff triggering pickup once an order is packaged
    (shipping/views.py:CreatePickupView) — not automatically on
    payment. Delivery orders only (FR-002), and only once payment has
    actually completed (FR-013) — both enforced here too as a last
    line of defense, even though the calling view already checks.

    On provider failure, records the failure on the Shipment row
    (FR-010) instead of raising — a booking failure must not blow up
    the caller.
    """
    if order.fulfillment_method != Order.FULFILLMENT_DELIVERY:
        return None
    if order.payment_status != Order.PAYMENT_STATUS_COMPLETE:
        raise ValueError(
            'Cannot book a shipment before payment has completed.')
    if not order.shipping_address:
        # No rate quote was ever requested for this order (shipping/
        # serializers.py RateQuoteSerializer) — nothing to book yet.
        # Not a failure: older orders/tests that predate this feature
        # simply have no shipment.
        return None

    shipment, _ = Shipment.objects.get_or_create(
        order=order, defaults={'provider': Shipment.PROVIDER_DAWUROBO})
    provider = get_provider(shipment.provider)

    try:
        result = provider.create_shipment(order, order.shipping_address)
    except ShippingProviderError:
        shipment.booking_failed = True
        shipment.save()
        return shipment

    shipment.tracking_reference = result['tracking_reference']
    shipment.carrier_name = 'Dawurobo'
    shipment.estimated_delivery_at = result.get('estimated_delivery_at')
    shipment.status = Shipment.STATUS_BOOKED
    shipment.booking_failed = False
    shipment.save()

    order.status = Order.STATUS_FULFILLMENT
    order.save()

    return shipment


def apply_shipment_status_update(shipment, new_status):
    """Advance `shipment` (and its order) to `new_status`, per the
    provider's webhook. Forward-only and idempotent (FR-007): a repeat
    of the current status, or a status that's behind where the
    shipment already is, is a no-op — so a duplicate or out-of-order
    webhook delivery never re-fires a notification or moves state
    backward.

    Returns True if a transition was actually applied.
    """
    if new_status not in dict(Shipment.STATUS_CHOICES):
        return False
    if new_status == shipment.status:
        return False  # exact repeat — the common duplicate-delivery case
    if new_status != Shipment.STATUS_DELIVERY_FAILED:
        old_rank = shipment.status_rank()
        new_rank = dict(zip(Shipment._STATUS_ORDER, range(len(Shipment._STATUS_ORDER)))).get(new_status, -1)
        if new_rank != -1 and new_rank <= old_rank:
            return False  # out-of-order/backward — ignore

    with transaction.atomic():
        shipment.status = new_status
        shipment.save()

        order = shipment.order
        order.status = _ORDER_STATUS_BY_SHIPMENT_STATUS[new_status]
        order.save()

    event = _NOTIFICATION_EVENT_BY_SHIPMENT_STATUS.get(new_status)
    if event:
        notify(order, event[0], event[1])

    return True
