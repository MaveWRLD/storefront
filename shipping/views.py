from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order

from .gateways import get_provider
from .models import Shipment
from .serializers import RateQuoteSerializer, ShipmentSerializer
from .services import apply_shipment_status_update, book_shipment_for_order, normalize_provider_status


class RateQuoteView(APIView):
    """Live shipping options for a delivery order. Open to guests too —
    guest checkout must not require an account to see shipping cost."""
    permission_classes = [AllowAny]

    @extend_schema(
        summary='Get shipping rate',
        description=(
            'Fetch a live delivery price + ETA for a delivery order and '
            'address, and persist it onto the order. Open to everyone.'))
    def post(self, request):
        serializer = RateQuoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(result)


class ShipmentDetailView(APIView):
    """Current shipment status for an order (FR-011). Open to everyone,
    same as the rest of this checkout flow (payment/views.py) — no
    account is required to place or pay for an order."""
    permission_classes = [AllowAny]

    @extend_schema(
        summary='Get shipment status',
        description='Tracking reference, carrier, and current status for an order\'s shipment. Open to everyone.')
    def get(self, request, order_id):
        shipment = get_object_or_404(Shipment, order_id=order_id)
        return Response(ShipmentSerializer(shipment).data)


class CreatePickupView(APIView):
    """store-admin/: staff trigger courier pickup once an order is
    packaged (sequence: customer pays -> Order.status=CONFIRMED ->
    staff packages -> staff calls this -> Dawurobo books the pickup).
    Not automatic on payment (see payment/serializers.py:confirm_payment
    for why) — booking a real courier is a deliberate staff action tied
    to the physical package being ready, same as OrderAdminViewSet's
    other staff-only order-lifecycle actions."""
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary='Create pickup',
        description=(
            'Book a Dawurobo pickup for a packaged, paid delivery order. '
            'Staff-only.'),
        responses={201: ShipmentSerializer})
    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)

        # Checked first: once booked, order.status has already moved
        # past CONFIRMED (book_shipment_for_order), so this must not
        # fall through to the "must be CONFIRMED" check below and
        # misreport an already-booked order as unpackaged.
        if Shipment.objects.filter(order=order).exists():
            return Response(
                {'detail': 'A pickup has already been created for this order.'},
                status=status.HTTP_409_CONFLICT)
        if order.fulfillment_method != Order.FULFILLMENT_DELIVERY:
            return Response(
                {'detail': 'Only delivery orders can have a pickup created.'},
                status=status.HTTP_400_BAD_REQUEST)
        if order.payment_status != Order.PAYMENT_STATUS_COMPLETE:
            return Response(
                {'detail': 'Order must be paid before a pickup can be created.'},
                status=status.HTTP_400_BAD_REQUEST)
        if order.status != Order.STATUS_CONFIRMED:
            return Response(
                {'detail': 'Order must be confirmed and packaged (status CONFIRMED) '
                           'before a pickup can be created.'},
                status=status.HTTP_400_BAD_REQUEST)
        if not order.shipping_address:
            return Response(
                {'detail': 'No shipping address on file — request a rate quote first.'},
                status=status.HTTP_400_BAD_REQUEST)

        shipment = book_shipment_for_order(order)
        return Response(ShipmentSerializer(shipment).data, status=status.HTTP_201_CREATED)


class ShippingWebhookView(APIView):
    """Dawurobo's shipment-status-update webhook — drives the order's
    fulfillment status forward as the courier makes progress (FR-006),
    the shipping-side equivalent of PaystackWebhookView.

    Every request must carry a valid provider signature; an
    unauthenticated POST is never trusted (FR-008).
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(exclude=True)
    def post(self, request):
        provider = get_provider(Shipment.PROVIDER_DAWUROBO)
        if not provider.verify_webhook_signature(
                request.body, request.headers.get('X-Webhook-Signature')):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        # Confirmed envelope (docs.dawurobo.com/docs/webhooks):
        # {service, event, version, data: {...}} — `event` is one of
        # order.created/accepted/rejected/picked_up/in_transit/
        # delivered/cancelled/rescheduled/returned/updated. The
        # `data` object's own field names weren't published, so the
        # correlation id is read tolerantly below; `data.status` is
        # preferred if present, else the envelope's `event` name itself
        # carries the status (normalize_provider_status handles both).
        payload = request.data
        data = payload.get('data', {})
        tracking_reference = (
            data.get('tracking_reference')
            or data.get('internal_order_id')
            or data.get('order_id')
            or data.get('order_reference'))
        new_status = data.get('status') or payload.get('event')
        if not tracking_reference or not new_status:
            return Response(status=status.HTTP_200_OK)

        try:
            shipment = Shipment.objects.select_related('order').get(
                tracking_reference=tracking_reference)
        except Shipment.DoesNotExist:
            return Response(status=status.HTTP_200_OK)  # unknown reference — nothing to reconcile

        normalized_status = normalize_provider_status(new_status)
        if normalized_status:
            apply_shipment_status_update(shipment, normalized_status)
        return Response(status=status.HTTP_200_OK)
