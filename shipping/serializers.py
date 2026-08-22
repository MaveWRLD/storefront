from djmoney.money import Money
from rest_framework import serializers

from orders.models import Order

from .gateways import ShippingProviderError, get_provider
from .models import Shipment


class AddressSerializer(serializers.Serializer):
    """The recipient contact + delivery address. Doubles as the sole
    guest-identity record on an Order (orders.models.Order.shipping_address)
    — recipient_name/email/phone are required here rather than living on
    Order directly, since Order carries no contact fields of its own.

    coordinates is required for Dawurobo's orders.estimate/orders.create
    (docs.dawurobo.com/docs/delivery-orders) — city/region/street_address
    are free text for the courier's own use, not what it prices against.
    ghana_post_gps is the optional GhanaPost digital-address code; nothing
    in this codebase resolves it to coordinates, so it's carried through
    as-is rather than substituting for them.

    coordinates is optional at this field level — a PICKUP order has no
    Dawurobo delivery to price, so it never needs them (no geocoding UI
    exists for a walk-in guest). Callers that DO need a delivery quote
    (RateQuoteSerializer, CreateOrderSerializer for a DELIVERY order)
    enforce it themselves in validate().
    """
    recipient_name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=32)
    street_address = serializers.CharField()
    city = serializers.CharField()
    region = serializers.CharField()
    ghana_post_gps = serializers.CharField(required=False, allow_blank=True, default='')
    coordinates = serializers.DictField(child=serializers.FloatField(), required=False)


class RateQuoteSerializer(serializers.Serializer):
    """Fetches a live delivery price/ETA for a delivery order (FR-001)
    and persists both the quoted cost (FR-003) and the address it was
    quoted against — Dawurobo re-prices at booking time rather than
    accepting a quote token back, so the address is what carries
    through to `shipping.services.book_shipment_for_order`
    (orders.Order.shipping_address, data-model.md).
    """
    order_id = serializers.IntegerField()
    # Optional: CreateOrderSerializer already persists an address onto
    # DELIVERY orders at creation time, so a caller that has nothing new
    # to quote against can omit this and fall back to what's on file.
    address = AddressSerializer(required=False)

    def validate_order_id(self, order_id):
        try:
            order = Order.objects.prefetch_related('items').get(pk=order_id)
        except Order.DoesNotExist:
            raise serializers.ValidationError('No order with the given ID was found.')
        if order.fulfillment_method != Order.FULFILLMENT_DELIVERY:
            # FR-002: pickup orders never get shipping options.
            raise serializers.ValidationError(
                'Shipping options only apply to delivery orders.')
        return order_id

    def validate(self, data):
        if not data.get('address'):
            order = Order.objects.get(pk=data['order_id'])
            if not order.shipping_address:
                raise serializers.ValidationError(
                    'No address given, and none on file for this order.')
            data['address'] = order.shipping_address
        # validate_order_id already enforces DELIVERY-only, so a quote
        # always needs coordinates to price against — even though the
        # AddressSerializer field itself is optional for PICKUP callers.
        if not data['address'].get('coordinates'):
            raise serializers.ValidationError(
                'The given address has no coordinates to quote against.')
        return data

    def save(self, **kwargs):
        order = Order.objects.prefetch_related('items').get(
            pk=self.validated_data['order_id'])
        address = self.validated_data['address']
        provider_name = Shipment.PROVIDER_DAWUROBO  # only provider registered so far

        try:
            estimate = get_provider(provider_name).get_rates(order, address)
        except ShippingProviderError as e:
            # Address the provider can't serve, or unreachable — either
            # way there's nothing to quote (spec.md edge case).
            raise serializers.ValidationError(str(e))

        order.shipping_cost = Money(estimate['cost'], order.subtotal_currency)
        order.shipping_address = address
        order.save()

        return {
            'cost': estimate['cost'],
            'estimated_delivery_at': estimate.get('estimated_delivery_at'),
            # Informational only (module docstring, shipping/gateways/
            # dawurobo.py) — Dawurobo's booking call can't honor a
            # customer-picked tier, so `cost` above (not one of these)
            # is what's charged and what gets booked.
            'options': estimate.get('options', []),
        }


class ShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = [
            'carrier_name', 'tracking_reference', 'status', 'cost',
            'estimated_delivery_at', 'booking_failed',
        ]
