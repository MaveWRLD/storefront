from uuid import uuid4

from rest_framework import serializers

from orders.models import Order
from .gateway import PaystackError, initialize_transaction, verify_transaction
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

        try:
            data = initialize_transaction(
                email=order.get_email(), amount=total.amount, reference=reference)
        except PaystackError as e:
            raise serializers.ValidationError(str(e))

        payment = Payment.objects.create(
            order=order, reference=reference, amount=total)
        return {'payment': payment, 'authorization_url': data['authorization_url']}


class VerifyPaymentSerializer(serializers.Serializer):
    reference = serializers.CharField()

    def validate_reference(self, reference):
        if not Payment.objects.filter(reference=reference).exists():
            raise serializers.ValidationError('No payment with the given reference was found.')
        return reference

    def save(self, **kwargs):
        payment = Payment.objects.select_related('order').get(
            reference=self.validated_data['reference'])

        try:
            data = verify_transaction(payment.reference)
        except PaystackError as e:
            raise serializers.ValidationError(str(e))

        if data.get('status') == 'success':
            payment.status = Payment.STATUS_SUCCESS
            payment.order.payment_status = Order.PAYMENT_STATUS_COMPLETE
        else:
            payment.status = Payment.STATUS_FAILED
            # Order stays PENDING (its default) so the customer can retry (US-11).

        payment.save()
        payment.order.save()
        return payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'order', 'reference', 'amount', 'status', 'created_at']
