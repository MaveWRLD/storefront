from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from orders.models import Order
from orders.serializers import OrderSerializer
from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(GenericViewSet):
    """store-front/: own profile only, no list/retrieve/create/delete."""
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Get or update my profile',
        description='GET returns the authenticated customer\'s own profile; PUT replaces it.')
    @action(detail=False, methods=['GET', 'PUT'])
    def me(self, request):
        customer = Customer.objects.get(
            user_id=request.user.id)
        if request.method == 'GET':
            serializer = CustomerSerializer(customer)
            return Response(serializer.data)
        elif request.method == 'PUT':
            serializer = CustomerSerializer(customer, data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        summary='List customers',
        description='List/search all customers by name, email, or phone. Staff-only.'),
    retrieve=extend_schema(
        summary='Get customer',
        description='Retrieve a single customer profile by id. Staff-only.'),
    create=extend_schema(
        summary='Create customer',
        description='Create a customer profile. Staff-only.'),
    update=extend_schema(
        summary='Replace customer',
        description='Full update of a customer profile. Staff-only.'),
    partial_update=extend_schema(
        summary='Update customer',
        description='Partial update of a customer profile. Staff-only.'),
    destroy=extend_schema(
        summary='Delete customer',
        description='Delete a customer profile. Staff-only.'),
)
class CustomerAdminViewSet(ModelViewSet):
    """store-admin/: 'admin searches for a customer... opens a customer's
    profile... sees the customer's details and order history.' (US-27)"""
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [SearchFilter]
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'phone']

    @extend_schema(
        summary='Get customer order history',
        description="List a customer's past orders. Staff-only.",
        responses=OrderSerializer(many=True))
    @action(detail=True, url_path='orders', url_name='orders')
    def orders(self, request, pk):
        orders = Order.objects.filter(
            customer_id=pk).prefetch_related('items__variant__product')
        return Response(OrderSerializer(orders, many=True).data)
