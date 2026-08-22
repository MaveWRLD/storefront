from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.mixins import (
    CreateModelMixin, DestroyModelMixin, ListModelMixin, RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.viewsets import GenericViewSet
from customers.models import Customer
from .models import Order
from .serializers import (
    CreateOrderSerializer, GuestOrderLookupSerializer, OrderSerializer,
    UpdateOrderSerializer,
)


@extend_schema_view(
    list=extend_schema(
        summary='List my orders',
        description='List the authenticated customer\'s own orders. Requires authentication.'),
    retrieve=extend_schema(
        summary='Get my order',
        description='Retrieve one of the authenticated customer\'s own orders by id. Requires authentication.'),
    create=extend_schema(
        summary='Place an order',
        description='Create an order from a cart. Open to guests (guest checkout).'),
)
class OrderViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """store-front/: create (guest checkout allowed), lookup (guest), and
    list/retrieve limited to the caller's own orders."""
    serializer_class = OrderSerializer

    def get_permissions(self):
        if self.action in ['create', 'lookup']:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_throttles(self):
        # IP-keyed, matching Spring's 20/min on guest order lookup/retrieve
        # (gap-analysis doc: 'No rate limiting anywhere') — enumeration by
        # order id + guessed email is exactly what this endpoint is open to.
        if self.action == 'lookup':
            self.throttle_scope = 'order-lookup'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def create(self, request, *args, **kwargs):
        user = request.user if request.user.is_authenticated else None
        serializer = CreateOrderSerializer(
            data=request.data,
            context={'user': user, 'request': request})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        serializer = OrderSerializer(
            order, context={'include_guest_token': True})
        return Response(serializer.data)

    @extend_schema(
        summary='Look up a guest order',
        description='Find a guest order by order number plus contact match. Open to everyone.')
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def lookup(self, request):
        serializer = GuestOrderLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data['order']
        return Response(OrderSerializer(order).data)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CreateOrderSerializer
        return OrderSerializer

    def get_queryset(self):
        customer_id = Customer.objects.only(
            'id').get(user_id=self.request.user.id)
        return Order.objects.filter(customer_id=customer_id)


@extend_schema_view(
    list=extend_schema(
        summary='List all orders',
        description='List every order in the system. Staff-only.'),
    retrieve=extend_schema(
        summary='Get order (admin)',
        description='Retrieve any order by id. Staff-only.'),
    partial_update=extend_schema(
        summary='Update order status',
        description='Update fulfillment/payment status or other fields on an order. Staff-only.'),
    destroy=extend_schema(
        summary='Delete order',
        description='Delete an order. Staff-only.'),
)
class OrderAdminViewSet(ListModelMixin, RetrieveModelMixin, UpdateModelMixin,
                         DestroyModelMixin, GenericViewSet):
    """store-admin/: list/retrieve all orders, update, destroy."""
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']
    queryset = Order.objects.all()
    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return UpdateOrderSerializer
        return OrderSerializer

    @extend_schema(
        summary='Total orders count',
        description='Return total number of orders in system. For dashboard. Staff-only.')
    @action(detail=False, methods=['get'])
    def count(self, request):
        return Response({'count': Order.objects.count()})
