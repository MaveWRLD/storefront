from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework import status
from .models import CartItem
from .serializers import (
    AddCartItemSerializer, CartItemSerializer, CartSerializer,
    UpdateCartItemSerializer,
)
from .services import get_current_cart, get_or_create_cart


@extend_schema_view(
    get=extend_schema(
        summary='Get my cart',
        description='Retrieve the current cart — the caller\'s (user or '
                    'guest session), created on first access. Open to everyone.'),
    delete=extend_schema(
        summary='Clear my cart',
        description='Discard the current cart and its items, if one exists. '
                    'Open to everyone.'),
)
class CartView(GenericAPIView):
    """store-front/cart/: the caller's own cart, resolved from the request
    (authenticated user, or the guest session's cart_id) — never addressed
    by id in the URL."""
    serializer_class = CartSerializer
    permission_classes = [AllowAny]

    def get(self, request):
        cart = get_or_create_cart(request)
        return Response(self.get_serializer(cart).data)

    def delete(self, request):
        cart = get_current_cart(request)
        if cart is not None:
            cart.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(
        summary='List cart items',
        description='List the items in the current cart. Open to everyone.'),
    retrieve=extend_schema(
        summary='Get cart item',
        description='Retrieve a single item from the current cart by id.'),
    create=extend_schema(
        summary='Add item to cart',
        description='Add a product variant to the current cart. Rejected if '
                    'the variant is out of stock or unavailable.'),
    partial_update=extend_schema(
        summary='Update cart item',
        description='Change a cart item\'s quantity.'),
    destroy=extend_schema(
        summary='Remove cart item',
        description='Remove an item from the current cart.'),
)
class CartItemViewSet(ModelViewSet):
    """store-front/cart/items/: items on the caller's own cart, same
    request-derived cart as CartView — no cart id in the URL."""
    http_method_names = ['get', 'post', 'patch', 'delete']
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AddCartItemSerializer
        elif self.request.method == 'PATCH':
            return UpdateCartItemSerializer
        return CartItemSerializer

    def get_serializer_context(self):
        return {'cart': get_or_create_cart(self.request)}

    def get_queryset(self):
        cart = get_or_create_cart(self.request)
        return CartItem.objects \
            .filter(cart=cart) \
            .select_related('variant__product')
