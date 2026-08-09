from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import CreateModelMixin, ListModelMixin, RetrieveModelMixin

from .models import Return
from .serializers import (
    CreateReturnSerializer, ReturnSerializer, ReviewReturnSerializer,
    order_matches_requester,
)


@extend_schema_view(
    create=extend_schema(
        summary='Request a return',
        description='Request a return for an order item. Open to guests (order number + contact match).'),
    retrieve=extend_schema(
        summary='Track a return',
        description='Retrieve a return by id. Ownership is checked in the view; guests must match order number + contact.'),
)
class ReturnViewSet(CreateModelMixin, RetrieveModelMixin, GenericViewSet):
    """store-front/: create and retrieve (ownership-checked; guest allowed
    via order number + contact match)."""
    queryset = Return.objects.select_related('order_item__order')
    serializer_class = ReturnSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        user = request.user if request.user.is_authenticated else None
        serializer = CreateReturnSerializer(
            data=request.data, context={'user': user})
        serializer.is_valid(raise_exception=True)
        return_request = serializer.save()
        return Response(
            ReturnSerializer(return_request).data, status=201)

    def retrieve(self, request, *args, **kwargs):
        return_request = self.get_object()
        if not request.user.is_staff:
            user = request.user if request.user.is_authenticated else None
            order = return_request.order_item.order
            if not order_matches_requester(
                    order, user, request.query_params.get('email', '')):
                raise PermissionDenied(
                    'This return does not belong to you.')
        return Response(ReturnSerializer(return_request).data)


@extend_schema_view(
    list=extend_schema(
        summary='List return requests',
        description='List all pending and reviewed return requests. Staff-only.'),
    partial_update=extend_schema(
        summary='Review a return',
        description='Approve or reject a return request; approving triggers a refund. Staff-only.'),
)
class ReturnAdminViewSet(ListModelMixin, GenericViewSet):
    """store-admin/: list, review (approve/reject) via partial_update
    (US-26/US-17: 'Only Admin can approve/reject a return')."""
    http_method_names = ['get', 'patch', 'head', 'options']
    queryset = Return.objects.select_related('order_item__order')
    serializer_class = ReturnSerializer
    permission_classes = [IsAdminUser]

    def partial_update(self, request, *args, **kwargs):
        return_request = self.get_object()
        serializer = ReviewReturnSerializer(
            instance=return_request, data=request.data)
        serializer.is_valid(raise_exception=True)
        return_request = serializer.save()
        return Response(ReturnSerializer(return_request).data)
