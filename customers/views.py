from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from orders.models import Order
from orders.serializers import OrderSerializer
from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(ModelViewSet):
    """US-27: 'admin searches for a customer... opens a customer's profile...
    sees the customer's details and order history.'"""
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [SearchFilter]
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'phone']

    @action(detail=True, permission_classes=[IsAdminUser])
    def history(self, request, pk):
        orders = Order.objects.filter(
            customer_id=pk).prefetch_related('items__variant__product')
        return Response(OrderSerializer(orders, many=True).data)

    @action(detail=False, methods=['GET', 'PUT'], permission_classes=[IsAuthenticated])
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
