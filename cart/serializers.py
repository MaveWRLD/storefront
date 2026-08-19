from django.conf import settings
from django.utils import timezone
from djmoney.money import Money
from rest_framework import serializers
from catalog.models import Variant
from catalog.serializers import SimpleVariantSerializer
from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    variant = SimpleVariantSerializer()
    total_price = serializers.SerializerMethodField()

    def get_total_price(self, cart_item: CartItem):
        return (cart_item.quantity * cart_item.variant.unit_price).amount

    class Meta:
        model = CartItem
        fields = ['id', 'variant', 'quantity', 'total_price']


class CartSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    items = CartItemSerializer(many=True, read_only=True)
    total_price = serializers.SerializerMethodField()

    def get_total_price(self, cart):
        total = sum(
            (item.quantity * item.variant.unit_price for item in cart.items.all()),
            start=Money(0, settings.DEFAULT_CURRENCY)
        )
        return total.amount

    class Meta:
        model = Cart
        fields = ['id', 'items', 'total_price']


class AddCartItemSerializer(serializers.ModelSerializer):
    variant_id = serializers.IntegerField()

    def validate_variant_id(self, value):
        if not Variant.objects.filter(pk=value).exists():
            raise serializers.ValidationError(
                'No variant with the given ID was found.')
        return value

    def validate(self, data):
        # Adapted from Saleor's check_stock_and_preorder_quantity: the requested
        # quantity must fit within stock once what's already sitting in this
        # cart for the same variant is accounted for. No Warehouse/Reservation
        # domain here (not built yet) — Variant.inventory is the whole stock signal.
        variant = Variant.objects.select_related('product').get(
            pk=data['variant_id'])

        # Business Rule (Catalog): 'Availability controlled via ProductStatus,
        # not a purchaseable flag' (US-22) — a DRAFT/ARCHIVED product can't be
        # added to cart regardless of stock.
        if not variant.product.is_available:
            raise serializers.ValidationError(
                'This product is not available for purchase.')

        cart = self.context['cart']
        already_in_cart = CartItem.objects.filter(
            cart=cart, variant_id=variant.id
        ).values_list('quantity', flat=True).first() or 0

        if variant.track_inventory and (
                variant.available <= 0
                or already_in_cart + data['quantity'] > variant.available):
            raise serializers.ValidationError(
                'This product does not have enough stock available.')
        return data

    def save(self, **kwargs):
        cart = self.context['cart']
        variant_id = self.validated_data['variant_id']
        quantity = self.validated_data['quantity']

        try:
            cart_item = CartItem.objects.get(
                cart=cart, variant_id=variant_id)
            cart_item.quantity += quantity
            cart_item.save()
            self.instance = cart_item
        except CartItem.DoesNotExist:
            self.instance = CartItem.objects.create(
                cart=cart, **self.validated_data)

        # Business Rule (Checkout): 'Abandoned checkout preserves the cart' —
        # touch the cart so its TTL clock (last_activity) resets on activity.
        Cart.objects.filter(pk=cart.pk).update(last_activity=timezone.now())

        return self.instance

    class Meta:
        model = CartItem
        fields = ['id', 'variant_id', 'quantity']


class UpdateCartItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = ['quantity']
