from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin, RetrieveModelMixin
from rest_framework.viewsets import ModelViewSet, GenericViewSet
from .models import Cart, CartItem
from .serializers import AddCartItemSerializer, CartItemSerializer, CartSerializer, UpdateCartItemSerializer


@extend_schema_view(
    create=extend_schema(
        summary='Create a cart',
        description='Start a new, empty cart. Open to everyone.'),
    retrieve=extend_schema(
        summary='Get cart',
        description='Retrieve a cart and its items by id. Open to everyone.'),
    destroy=extend_schema(
        summary='Delete cart',
        description='Discard a cart and its items. Open to everyone.'),
)
class CartViewSet(CreateModelMixin,
                  RetrieveModelMixin,
                  DestroyModelMixin,
                  GenericViewSet):
    queryset = Cart.objects.prefetch_related('items__variant__product').all()
    serializer_class = CartSerializer


@extend_schema_view(
    list=extend_schema(
        summary='List cart items',
        description='List the items in a cart. Open to everyone.'),
    retrieve=extend_schema(
        summary='Get cart item',
        description='Retrieve a single cart item by id. Open to everyone.'),
    create=extend_schema(
        summary='Add item to cart',
        description='Add a product variant to the cart. Rejected if the variant is out of stock or unavailable.'),
    partial_update=extend_schema(
        summary='Update cart item',
        description='Change a cart item\'s quantity.'),
    destroy=extend_schema(
        summary='Remove cart item',
        description='Remove an item from the cart.'),
)
class CartItemViewSet(ModelViewSet):
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AddCartItemSerializer
        elif self.request.method == 'PATCH':
            return UpdateCartItemSerializer
        return CartItemSerializer

    def get_serializer_context(self):
        return {'cart_id': self.kwargs['cart_pk']}

    def get_queryset(self):
        return CartItem.objects \
            .filter(cart_id=self.kwargs['cart_pk']) \
            .select_related('variant__product')
