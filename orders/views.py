from rest_framework.decorators import action
from rest_framework.mixins import (
    CreateModelMixin, DestroyModelMixin, ListModelMixin, RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from customers.models import Customer
from .models import Order
from .serializers import (
    CreateOrderSerializer, GuestOrderLookupSerializer, OrderSerializer,
    UpdateOrderSerializer,
)


class OrderViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, GenericViewSet):
    """store-front/: create (guest checkout allowed), lookup (guest), and
    list/retrieve limited to the caller's own orders."""
    serializer_class = OrderSerializer

    def get_permissions(self):
        if self.action in ['create', 'lookup']:
            return [AllowAny()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        user = request.user if request.user.is_authenticated else None
        serializer = CreateOrderSerializer(
            data=request.data,
            context={'user': user})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        serializer = OrderSerializer(order)
        return Response(serializer.data)

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
