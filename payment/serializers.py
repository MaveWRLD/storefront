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
    order_id = serializers.IntegerField()

    def validate_order_id(self, order_id):
        try:
            order = Order.objects.prefetch_related('items').get(pk=order_id)
        except Order.DoesNotExist:
            raise serializers.ValidationError('No order with the given ID was found.')
        if order.payment_status == Order.PAYMENT_STATUS_COMPLETE:
            raise serializers.ValidationError('This order has already been paid for.')
        return order_id

    def save(self, **kwargs):
        order = Order.objects.get(pk=self.validated_data['order_id'])
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
    reference = serializers.CharField()

    def validate_reference(self, reference):
        if not Payment.objects.filter(reference=reference).exists():
            raise serializers.ValidationError('No payment with the given reference was found.')
        return reference

    def save(self, **kwargs):
        try:
            return confirm_payment(self.validated_data['reference'])
        except PaymentGatewayError as e:
            raise serializers.ValidationError(str(e))


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'order', 'reference', 'amount', 'status', 'created_at']
