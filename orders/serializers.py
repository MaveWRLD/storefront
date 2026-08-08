from django.db import transaction
from rest_framework import serializers
from cart.models import Cart, CartItem
from catalog.serializers import SimpleProductSerializer
from customers.models import Customer
from .models import Order, OrderItem
from .signals import order_created


class OrderItemSerializer(serializers.ModelSerializer):
    product = SimpleProductSerializer()

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'unit_price', 'quantity']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = ['id', 'customer', 'guest_name', 'guest_email',
                  'placed_at', 'payment_status', 'items']


class UpdateOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['payment_status']


class CreateOrderSerializer(serializers.Serializer):
    """Places an order from a cart.

    Adapted from Saleor's checkout-completion pattern (a Checkout with no
    `user` set still carries `email`, so completing it doesn't require an
    account): an authenticated request resolves its Customer as before;
    an anonymous request must supply guest contact details instead.
    """
    cart_id = serializers.UUIDField()
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
        return data

    def save(self, **kwargs):
        with transaction.atomic():
            cart_id = self.validated_data['cart_id']
            user = self.context.get('user')

            if user is not None and user.is_authenticated:
                customer = Customer.objects.get(user_id=user.id)
                order = Order.objects.create(customer=customer)
            else:
                order = Order.objects.create(
                    guest_name=self.validated_data.get('guest_name', ''),
                    guest_email=self.validated_data.get('guest_email', ''),
                    guest_phone=self.validated_data.get('guest_phone', ''),
                )

            cart_items = CartItem.objects \
                .select_related('product') \
                .filter(cart_id=cart_id)
            order_items = [
                OrderItem(
                    order=order,
                    product=item.product,
                    unit_price=item.product.unit_price,
                    quantity=item.quantity
                ) for item in cart_items
            ]
            OrderItem.objects.bulk_create(order_items)

            Cart.objects.filter(pk=cart_id).delete()

            order_created.send_robust(self.__class__, order=order)

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
