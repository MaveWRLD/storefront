from django.utils import timezone
from rest_framework import serializers

from notifications.models import Notification
from notifications.services import notify
from orders.models import Order, OrderItem
from payment.gateways import PaymentGatewayError, get_gateway
from payment.models import Payment
from .models import Return


def order_matches_requester(order, user, email):
    """Shared ownership check — Business Rule (Returns & Refunds): 'Guests
    manage returns via order number + contact match', same match used for
    both requesting (US-16) and tracking (US-17) a return."""
    if order.customer_id:
        return user is not None and user.is_authenticated \
            and order.customer.user_id == user.id
    return bool(email) and email.lower() == order.guest_email.lower()


class CreateReturnSerializer(serializers.Serializer):
    """US-16: request a return on a completed order.

    Adapted from orders.serializers.GuestOrderLookupSerializer's order id +
    email match — Business Rule (Returns & Refunds): 'Guests manage returns
    via order number + contact match'.
    """
    order_id = serializers.IntegerField()
    order_item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField()
    email = serializers.EmailField(required=False)

    def validate(self, data):
        try:
            order = Order.objects.get(pk=data['order_id'])
        except Order.DoesNotExist:
            raise serializers.ValidationError('No matching order was found.')

        user = self.context.get('user')
        if not order_matches_requester(order, user, data.get('email', '')):
            raise serializers.ValidationError(
                'This order does not belong to you.')

        # Given a customer has a completed order — no fixed return window
        # is enforced (Business Rule: 'No fixed return window — Admin
        # decides case by case'), only that the order has been completed.
        if order.status != Order.STATUS_COMPLETED:
            raise serializers.ValidationError(
                'Returns can only be requested on a completed order.')

        try:
            order_item = order.items.get(pk=data['order_item_id'])
        except OrderItem.DoesNotExist:
            raise serializers.ValidationError(
                'This item was not found on the given order.')

        if data['quantity'] > order_item.quantity:
            raise serializers.ValidationError(
                'Return quantity cannot exceed the quantity ordered.')

        data['order_item'] = order_item
        return data

    def save(self, **kwargs):
        return Return.objects.create(
            order_item=self.validated_data['order_item'],
            quantity=self.validated_data['quantity'],
            reason=self.validated_data['reason'],
        )


class ReturnSerializer(serializers.ModelSerializer):
    instructions = serializers.SerializerMethodField()

    def get_instructions(self, return_request):
        return (
            'Pack the item securely and ship it back using the address on '
            'your order confirmation. We will review it once received.'
        )

    class Meta:
        model = Return
        fields = ['id', 'order_item', 'quantity', 'reason', 'status',
                  'requested_at', 'resolution_reason', 'reviewed_at',
                  'instructions']


class ReviewReturnSerializer(serializers.Serializer):
    """US-17/US-26 — admin approves or rejects a reviewed return.

    Business Rule (Returns & Refunds): 'Rejected return: item back to
    customer, no refund; approved: Paystack refund'. Adapted from Saleor's
    order/actions.py refund orchestration, scaled down to a single full
    refund against the order's successful Payment — no partial-amount or
    multi-gateway support (Business Rule: Paystack is the only gateway).
    """
    ACTION_APPROVE = 'approve'
    ACTION_REJECT = 'reject'

    action = serializers.ChoiceField(choices=[ACTION_APPROVE, ACTION_REJECT])
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        return_request = self.instance
        if return_request.status != Return.STATUS_PENDING_REVIEW:
            raise serializers.ValidationError(
                'This return has already been reviewed.')

        if data['action'] == self.ACTION_REJECT and not data.get('reason'):
            raise serializers.ValidationError(
                'A reason is required to reject a return.')

        if data['action'] == self.ACTION_APPROVE:
            order = return_request.order_item.order
            payment = Payment.objects.filter(
                order=order, status=Payment.STATUS_SUCCESS).first()
            if payment is None:
                raise serializers.ValidationError(
                    'No successful payment was found on this order to refund.')
            data['payment'] = payment

        return data

    def save(self, **kwargs):
        return_request = self.instance
        if self.validated_data['action'] == self.ACTION_APPROVE:
            payment = self.validated_data['payment']
            try:
                get_gateway(payment.gateway).refund_transaction(payment.reference)
            except PaymentGatewayError as e:
                raise serializers.ValidationError(str(e))
            return_request.status = Return.STATUS_APPROVED
            message = 'Your return was approved and a refund has been issued.'
        else:
            return_request.status = Return.STATUS_REJECTED
            return_request.resolution_reason = self.validated_data['reason']
            message = f"Your return was rejected: {self.validated_data['reason']}"

        return_request.reviewed_at = timezone.now()
        return_request.save()

        # Business Rule (Notifications): 'Customer notified at every
        # status-changing milestone' — a return's approve/reject decision
        # is one of those milestones.
        notify(
            return_request.order_item.order,
            Notification.EVENT_REFUND_DECISION, message)

        return return_request
