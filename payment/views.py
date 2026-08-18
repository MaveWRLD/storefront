from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .gateways import get_gateway
from .models import Payment
from .serializers import (
    InitializePaymentSerializer, PaymentSerializer, VerifyPaymentSerializer,
    confirm_payment,
)


class InitializePaymentView(APIView):
    """Starts a Paystack transaction for an order. Open to guests too —
    guest checkout (US-06a) must not require an account to pay."""
    permission_classes = [AllowAny]

    @extend_schema(
        summary='Initialize payment',
        description='Start a Paystack transaction for an order and return its authorization URL. Open to everyone.')
    def post(self, request):
        serializer = InitializePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response({
            'reference': result['payment'].reference,
            'authorization_url': result['authorization_url'],
        })


class VerifyPaymentView(APIView):
    """Checks a transaction's outcome with Paystack and updates the order.

    Fast UX path for a customer waiting on the result. The Paystack
    webhook (PaystackWebhookView) is the source-of-truth safety net for
    customers who close the tab before this call ever fires.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary='Verify payment',
        description='Check a transaction\'s outcome with Paystack and update the order accordingly. Open to everyone.')
    def post(self, request):
        serializer = VerifyPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        return Response(PaymentSerializer(payment).data)


class PaystackWebhookView(APIView):
    """P1: Paystack's `charge.success` webhook — the reconciliation
    safety net for VerifyPaymentView. A customer closing the tab right
    after paying leaves the order PENDING forever if nothing but the
    client-driven poll ever runs this confirm logic; Paystack calls this
    endpoint independent of any client action.

    Every request must carry a valid `x-paystack-signature` (HMAC-SHA512
    of the raw body, keyed on PAYSTACK_SECRET_KEY) — an unauthenticated
    POST is never trusted. Always acks with 200 once the signature and
    event are handled, per Paystack's retry contract, except when the
    Paystack API itself is unreachable (503, so Paystack retries).
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(exclude=True)
    def post(self, request):
        gateway = get_gateway(Payment.GATEWAY_PAYSTACK)
        if not gateway.verify_webhook_signature(
                request.body, request.headers.get('x-paystack-signature')):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        event = request.data
        if event.get('event') != 'charge.success':
            return Response(status=status.HTTP_200_OK)

        reference = event.get('data', {}).get('reference')
        if not reference:
            return Response(status=status.HTTP_200_OK)

        try:
            confirm_payment(reference, transaction_data=event['data'])
        except Payment.DoesNotExist:
            pass  # unknown reference — nothing to reconcile, ack anyway

        return Response(status=status.HTTP_200_OK)
