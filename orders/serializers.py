from django.db import models, transaction
from rest_framework import serializers
from cart.models import Cart, CartItem
from catalog.models import Variant
from catalog.serializers import SimpleVariantSerializer
from customers.models import Customer
from notifications.models import Notification
from notifications.services import notify
from .models import Order, OrderItem
from .signals import order_created

# Business Rule (Notifications): 'Customer notified at every status-changing
# milestone' — only the milestones named in US-18 (confirmed, ready for
# pickup, out for delivery, delivered); ORDER_CONFIRMED is notified from
# payment/serializers.py instead, since that's where it's actually set.
_MILESTONE_NOTIFICATIONS = {
    Order.STATUS_READY_FOR_PICKUP: (
        Notification.EVENT_READY_FOR_PICKUP,
        'Your order is ready for pickup.'),
    Order.STATUS_OUT_FOR_DELIVERY: (
        Notification.EVENT_OUT_FOR_DELIVERY,
        'Your order is out for delivery.'),
    Order.STATUS_COMPLETED: (
        Notification.EVENT_DELIVERED,
        'Your order has been delivered.'),
}


class OrderItemSerializer(serializers.ModelSerializer):
    variant = SimpleVariantSerializer()

    class Meta:
        model = OrderItem
        fields = ['id', 'variant', 'unit_price', 'quantity']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    unavailable_items = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ['id', 'customer', 'guest_name', 'guest_email',
                  'fulfillment_method', 'placed_at', 'payment_status', 'status',
                  'items', 'unavailable_items']

    def get_unavailable_items(self, order):
        # Not persisted (US-09): the checkout-time stock re-check drops these
        # lines before the order is created, so there's nothing in the DB to
        # query back — CreateOrderSerializer.save() stashes them on the
        # in-memory instance for this one response, so the customer is told
        # before payment which items got dropped.
        return getattr(order, 'unavailable_items', [])


class UpdateOrderSerializer(serializers.ModelSerializer):
    """Admin-only order updates, including fulfillment status (US-24).

    Business Rule (Shipping): 'Every order follows exactly one fulfillment
    path (Pickup or Delivery)' — enforced here again, not just at order
    creation: READY_FOR_PICKUP/OUT_FOR_DELIVERY must match the order's own
    fulfillment_method, mirroring Saleor's fulfillment-vs-delivery-method
    consistency checks in orders/actions.py.
    """
    # Stages an admin can move an order into. CONFIRMED is set automatically
    # on payment success (US-13), never by this endpoint.
    _PROGRESSION = [
        Order.STATUS_CONFIRMED,
        Order.STATUS_FULFILLMENT,
        Order.STATUS_READY_FOR_PICKUP,
        Order.STATUS_OUT_FOR_DELIVERY,
        Order.STATUS_COMPLETED,
    ]

    class Meta:
        model = Order
        fields = ['payment_status', 'status']

    def validate_status(self, value):
        if value == Order.STATUS_CONFIRMED:
            raise serializers.ValidationError(
                'Orders are confirmed automatically on payment, not set manually.')

        order = self.instance
        known_stages = set(self._PROGRESSION) | {
            Order.STATUS_DELIVERY_FAILED, Order.STATUS_PENDING_RESOLUTION,
            Order.STATUS_CANCELLED}
        if value not in known_stages:
            raise serializers.ValidationError('Unknown fulfillment stage.')
        if not order.status or order.payment_status != Order.PAYMENT_STATUS_COMPLETE:
            raise serializers.ValidationError(
                'Order must be paid and confirmed before it can be fulfilled.')

        # US-25: cancelled is terminal — no further transitions out of it.
        if order.status == Order.STATUS_CANCELLED:
            raise serializers.ValidationError(
                'This order has been cancelled and cannot be updated further.')
        if value == Order.STATUS_CANCELLED and order.status not in (
                Order.STATUS_DELIVERY_FAILED, Order.STATUS_PENDING_RESOLUTION):
            raise serializers.ValidationError(
                'Only a failed delivery or an unresolved pickup can be cancelled.')

        # US-15/US-25: flagging or rescheduling a failed delivery is a
        # side-branch off OUT_FOR_DELIVERY, not part of the linear
        # progression below.
        if value == Order.STATUS_DELIVERY_FAILED:
            if order.fulfillment_method != Order.FULFILLMENT_DELIVERY \
                    or order.status != Order.STATUS_OUT_FOR_DELIVERY:
                raise serializers.ValidationError(
                    'Only an order currently Out for Delivery can be flagged as failed.')
            return value
        if order.status == Order.STATUS_DELIVERY_FAILED:
            # US-25: give up instead of rescheduling — return the line(s) to
            # inventory (Business Rule: 'Failed delivery triggers reschedule,
            # not auto-cancel' — cancelling is still an explicit admin
            # decision, never automatic).
            if value not in (Order.STATUS_OUT_FOR_DELIVERY, Order.STATUS_CANCELLED):
                raise serializers.ValidationError(
                    'A failed delivery can only be rescheduled back to Out for '
                    'Delivery, or cancelled and returned to inventory.')
            return value

        # US-14: flagging an uncollected pickup as pending resolution is a
        # side-branch off READY_FOR_PICKUP, same shape as DELIVERY_FAILED
        # above. Business Rule (Shipping): 'No fixed pickup window — Admin
        # decides case by case' — this is always an explicit admin action,
        # never a scheduled timer.
        if value == Order.STATUS_PENDING_RESOLUTION:
            if order.fulfillment_method != Order.FULFILLMENT_PICKUP \
                    or order.status != Order.STATUS_READY_FOR_PICKUP:
                raise serializers.ValidationError(
                    "Only an order currently Ready for Pickup can be flagged as pending resolution.")
            return value
        if order.status == Order.STATUS_PENDING_RESOLUTION:
            # US-25: give-up-and-restock path for an unresolved pickup no-show.
            if value not in (Order.STATUS_COMPLETED, Order.STATUS_CANCELLED):
                raise serializers.ValidationError(
                    'A pending-resolution pickup can only move forward to '
                    'Completed once collected, or be cancelled and returned to inventory.')
            return value

        if self._PROGRESSION.index(value) <= self._PROGRESSION.index(order.status):
            raise serializers.ValidationError(
                'Fulfillment status cannot move backward.')

        if value == Order.STATUS_READY_FOR_PICKUP and order.fulfillment_method != Order.FULFILLMENT_PICKUP:
            raise serializers.ValidationError(
                "Only Pickup orders can be marked 'Ready for Pickup'.")
        if value == Order.STATUS_OUT_FOR_DELIVERY and order.fulfillment_method != Order.FULFILLMENT_DELIVERY:
            raise serializers.ValidationError(
                "Only Delivery orders can be marked 'Out for Delivery'.")

        return value

    def update(self, instance, validated_data):
        order = super().update(instance, validated_data)

        if order.status == Order.STATUS_CANCELLED:
            # Business Rule (Shipping): 'Failed delivery triggers reschedule,
            # not auto-cancel' — the give-up path, US-25: return each line's
            # stock so an abandoned order doesn't just lose it.
            #
            # Business Rule (Warehouse): 'Stock decrements only on payment
            # success, not at checkout' (US-33) — branch on payment_status:
            # a paid order already had `inventory` physically decremented
            # (and `allocated` released) at payment success (US-31), so
            # crediting `inventory` back is correct and `allocated` needs no
            # further change. An unpaid order never touched `inventory` —
            # its stock was only ever held in `allocated`, so that's what
            # must be released instead.
            for item in order.items.select_related('variant'):
                if order.payment_status == Order.PAYMENT_STATUS_COMPLETE:
                    Variant.objects.filter(pk=item.variant_id).update(
                        inventory=models.F('inventory') + item.quantity)
                else:
                    Variant.objects.filter(pk=item.variant_id).update(
                        allocated=models.F('allocated') - item.quantity)

        notification = _MILESTONE_NOTIFICATIONS.get(order.status)
        if notification is not None:
            event_type, message = notification
            notify(order, event_type, message)
        return order


class CreateOrderSerializer(serializers.Serializer):
    """Places an order from a cart.

    Adapted from Saleor's checkout-completion pattern (a Checkout with no
    `user` set still carries `email`, so completing it doesn't require an
    account): an authenticated request resolves its Customer as before;
    an anonymous request must supply guest contact details instead.
    """
    cart_id = serializers.UUIDField()
    fulfillment_method = serializers.ChoiceField(
        choices=Order.FULFILLMENT_METHOD_CHOICES)
    guest_name = serializers.CharField(required=False, allow_blank=True)
    guest_email = serializers.EmailField(required=False)
    guest_phone = serializers.CharField(
        required=False, allow_blank=True, max_length=32)

    def validate_cart_id(self, cart_id):
        if not Cart.objects.filter(pk=cart_id).exists():
            raise serializers.ValidationError(
                'No cart with the given ID was found.')
        if CartItem.objects.filter(cart_id=cart_id).count() == 0:
            raise serializers.ValidationError('The cart is empty.')
        return cart_id

    def validate(self, data):
        user = self.context.get('user')
        if user is None or not user.is_authenticated:
            if not data.get('guest_name') or not data.get('guest_email'):
                raise serializers.ValidationError(
                    'Guest checkout requires guest_name and guest_email.')

        # Business Rule (Warehouse): 'Stock re-validated at checkout, not
        # just add-to-cart' (US-09). Adapted from Saleor's
        # check_stock_and_preorder_quantity, called again at checkout
        # completion instead of trusting the add-to-cart check: a product
        # can go DRAFT/ARCHIVED or run out of stock while it's still sitting
        # in someone's cart.
        cart_items = list(
            CartItem.objects
            .select_related('variant__product')
            .filter(cart_id=data['cart_id']))
        available, unavailable = [], []
        for item in cart_items:
            variant = item.variant
            in_stock = not variant.track_inventory or variant.available >= item.quantity
            if variant.product.is_available and in_stock:
                available.append(item)
            else:
                unavailable.append(item)

        if not available:
            raise serializers.ValidationError(
                'None of the items in your cart are currently available.')

        data['_available_items'] = available
        data['_unavailable_items'] = unavailable
        return data

    def save(self, **kwargs):
        with transaction.atomic():
            user = self.context.get('user')
            fulfillment_method = self.validated_data['fulfillment_method']

            if user is not None and user.is_authenticated:
                customer = Customer.objects.get(user_id=user.id)
                order = Order.objects.create(
                    customer=customer, fulfillment_method=fulfillment_method)
            else:
                order = Order.objects.create(
                    fulfillment_method=fulfillment_method,
                    guest_name=self.validated_data.get('guest_name', ''),
                    guest_email=self.validated_data.get('guest_email', ''),
                    guest_phone=self.validated_data.get('guest_phone', ''),
                )

            available_items = self.validated_data['_available_items']
            unavailable_items = self.validated_data['_unavailable_items']

            # Business Rule (Warehouse): 'Stock decrements only on payment
            # success, not at checkout' (US-30). validate() already
            # re-checked stock, but unlocked — lock the candidate variants
            # and recheck under the lock to close the checkout race two
            # concurrent checkouts on the last unit could otherwise both
            # pass validate() and both reach here. Only `allocated` is
            # bumped; `inventory` is untouched until payment succeeds.
            locked_variants = {
                v.pk: v for v in Variant.objects.select_for_update().filter(
                    pk__in=[item.variant_id for item in available_items]
                ).order_by('pk')
            }

            order_items = []
            for item in available_items:
                variant = locked_variants[item.variant_id]
                if variant.track_inventory and variant.available < item.quantity:
                    unavailable_items.append(item)
                    continue
                order_items.append(OrderItem(
                    order=order,
                    variant=item.variant,
                    unit_price=item.variant.unit_price,
                    quantity=item.quantity,
                ))
                Variant.objects.filter(pk=variant.pk).update(
                    allocated=models.F('allocated') + item.quantity)

            if not order_items:
                raise serializers.ValidationError(
                    'None of the items in your cart are currently available.')

            OrderItem.objects.bulk_create(order_items)

            Cart.objects.filter(pk=self.validated_data['cart_id']).delete()

            order_created.send_robust(self.__class__, order=order)

            # Transient, not persisted — see OrderSerializer.get_unavailable_items.
            order.unavailable_items = [
                {'product_id': item.variant.product_id,
                'title': item.variant.product.title,
                'reason': 'out_of_stock' if item.variant.product.is_available else 'unavailable'}
                for item in unavailable_items
            ]
            return order


class GuestOrderLookupSerializer(serializers.Serializer):
    """CheckoutService.getGuestOrder(orderId, email), adapted: a guest looks
    up their own order by order id + the email they checked out with, no
    login required."""
    order_id = serializers.IntegerField()
    email = serializers.EmailField()

    def validate(self, data):
        try:
            order = Order.objects.get(
                pk=data['order_id'], guest_email__iexact=data['email'])
        except Order.DoesNotExist:
            raise serializers.ValidationError(
                'No matching guest order was found.')
        data['order'] = order
        return data
