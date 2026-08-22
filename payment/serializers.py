from uuid import uuid4

from django.db import models, transaction
from rest_framework import serializers

from catalog.models import Variant
from notifications.models import Notification
from notifications.services import notify
from orders.models import Order
from .gateways import PaymentGatewayError, get_gateway
from .models import Payment


class InitializePaymentSerializer(serializers.Serializer):
    """Requires proof of order ownership — order_id alone isn't enough,
    since ids are sequential and guessable. A guest order (no customer)
    proves ownership with guest_token, the write-once secret returned by
    order creation (orders/serializers.py:OrderSerializer); an
    authenticated order proves it by request.user owning the order's
    customer. Without this, anyone who guesses an order_id could start a
    Paystack transaction against someone else's order."""
    order_id = serializers.IntegerField()
    guest_token = serializers.CharField(required=False)

    def validate_order_id(self, order_id):
        try:
            order = Order.objects.prefetch_related('items').get(pk=order_id)
        except Order.DoesNotExist:
            raise serializers.ValidationError('No order with the given ID was found.')
        if order.payment_status == Order.PAYMENT_STATUS_COMPLETE:
            raise serializers.ValidationError('This order has already been paid for.')
        self._order = order
        return order_id

    def validate(self, data):
        order = self._order
        request = self.context['request']
        if order.customer_id is not None:
            user = request.user
            is_owner = user.is_authenticated and \
                getattr(order.customer, 'user_id', None) == user.id
            if not is_owner:
                raise serializers.ValidationError(
                    'You do not have permission to pay for this order.')
        elif data.get('guest_token') != order.guest_token:
            raise serializers.ValidationError(
                'You do not have permission to pay for this order.')

        # A DELIVERY order gets its shipping_cost from POST /shipping/rates/
        # (shipping/serializers.py:RateQuoteSerializer.save) — that's a
        # separate frontend step, not enforced by order creation, so
        # nothing otherwise stops a caller going straight from create ->
        # pay and shipping the order for free (Order.shipping_cost
        # defaults to 0, orders/models.py).
        if order.fulfillment_method == Order.FULFILLMENT_DELIVERY \
                and order.shipping_cost.amount == 0:
            raise serializers.ValidationError(
                'This order has no shipping rate yet — call '
                '/shipping/rates/ before paying.')
        return data

    def save(self, **kwargs):
        order = self._order
        reference = uuid4().hex
        total = order.get_total()
        gateway_name = Payment.GATEWAY_PAYSTACK  # only gateway registered so far

        try:
            data = get_gateway(gateway_name).initialize_transaction(
                email=order.get_email(), amount=total.amount, reference=reference)
        except PaymentGatewayError as e:
            raise serializers.ValidationError(str(e))

        payment = Payment.objects.create(
            order=order, reference=reference, amount=total, gateway=gateway_name)
        return {'payment': payment, 'authorization_url': data['authorization_url']}


def confirm_payment(reference, transaction_data=None):
    """Apply a Paystack transaction outcome to its Payment/Order.

    Shared by the customer-driven verify poll (VerifyPaymentSerializer)
    and the Paystack webhook (P1) — same confirm logic, either path can
    be first to land. Idempotent: a payment that's already left PENDING
    is returned as-is, so a webhook arriving after (or racing) a poll
    verify never double-decrements stock.

    `transaction_data` lets a caller that already has a trustworthy
    outcome (the webhook's HMAC-verified body) skip the extra Paystack
    API round-trip; omit it to ask Paystack directly (the poll path).
    """
    payment = Payment.objects.select_related('order').get(reference=reference)
    if payment.status != Payment.STATUS_PENDING:
        return payment

    data = transaction_data if transaction_data is not None \
        else get_gateway(payment.gateway).verify_transaction(payment.reference)

    with transaction.atomic():
        if data.get('status') == 'success':
            payment.status = Payment.STATUS_SUCCESS
            payment.order.payment_status = Order.PAYMENT_STATUS_COMPLETE
            payment.order.status = Order.STATUS_CONFIRMED

            # Business Rule (Warehouse): 'Stock decrements only on
            # payment success, not at checkout' (US-31). This is the
            # only place Variant.inventory physically drops — checkout
            # (US-30) only ever bumps `allocated`. Lock each order
            # line's variant and decrement inventory/allocated together.
            order_items = list(
                payment.order.items.select_related('variant'))
            locked_variants = {
                v.pk: v for v in Variant.objects.select_for_update().filter(
                    pk__in=[item.variant_id for item in order_items]
                ).order_by('pk')
            }
            for item in order_items:
                variant = locked_variants[item.variant_id]
                if not variant.track_inventory:
                    continue
                Variant.objects.filter(pk=variant.pk).update(
                    inventory=models.F('inventory') - item.quantity,
                    allocated=models.F('allocated') - item.quantity,
                )
        else:
            payment.status = Payment.STATUS_FAILED
            # Order stays PENDING (its default) so the customer can retry (US-11).

        payment.save()
        payment.order.save()

    if payment.status == Payment.STATUS_SUCCESS:
        # Business Rule (Notifications): 'Customer notified at every
        # status-changing milestone'.
        notify(
            payment.order, Notification.EVENT_ORDER_CONFIRMED,
            'Your order has been confirmed.')

        # 004-shipping-integration: shipment booking is NOT triggered
        # here. Staff physically package a CONFIRMED order first, then
        # trigger booking themselves (shipping/views.py:CreatePickupView,
        # store-admin/) — payment confirmation and courier pickup are
        # separate real-world events, not one atomic step.

    return payment


class VerifyPaymentSerializer(serializers.Serializer):
    """Same ownership proof as InitializePaymentSerializer, checked
    against the payment's order — a guessed/leaked reference alone isn't
    enough to poll (and thus confirm) someone else's payment."""
    reference = serializers.CharField()
    guest_token = serializers.CharField(required=False)

    def validate_reference(self, reference):
        try:
            self._payment = Payment.objects.select_related('order__customer').get(
                reference=reference)
        except Payment.DoesNotExist:
            raise serializers.ValidationError('No payment with the given reference was found.')
        return reference

    def validate(self, data):
        order = self._payment.order
        request = self.context['request']
        if order.customer_id is not None:
            user = request.user
            is_owner = user.is_authenticated and \
                getattr(order.customer, 'user_id', None) == user.id
            if not is_owner:
                raise serializers.ValidationError(
                    'You do not have permission to view this payment.')
        elif data.get('guest_token') != order.guest_token:
            raise serializers.ValidationError(
                'You do not have permission to view this payment.')
        return data

    def save(self, **kwargs):
        try:
            return confirm_payment(self.validated_data['reference'])
        except PaymentGatewayError as e:
            raise serializers.ValidationError(str(e))


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'order', 'reference', 'amount', 'status', 'created_at']
