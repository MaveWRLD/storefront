from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    InitializePaymentSerializer, PaymentSerializer, VerifyPaymentSerializer,
)


class InitializePaymentView(APIView):
    """Starts a Paystack transaction for an order. Open to guests too —
    guest checkout (US-06a) must not require an account to pay."""
    permission_classes = [AllowAny]

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

    A real deployment would also register a Paystack webhook so a customer
    closing the tab mid-payment doesn't leave the order stuck pending;
    that's deferred here (see US-10 write-up) in favor of this
    customer-driven verify call, which already satisfies the story's own
    acceptance criteria.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        return Response(PaymentSerializer(payment).data)
