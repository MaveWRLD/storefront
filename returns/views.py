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


class ReturnViewSet(CreateModelMixin, ListModelMixin, RetrieveModelMixin, GenericViewSet):
    queryset = Return.objects.select_related('order_item__order')
    serializer_class = ReturnSerializer

    def get_permissions(self):
        # US-26/US-17: 'Only Admin can approve/reject a return' — reviewing
        # (including browsing the list to find something to review) is
        # admin-only; requesting and tracking a single one stay open to
        # guests too (Business Rule: 'Guests manage returns via order
        # number + contact match'), ownership is checked inside
        # create()/retrieve() instead.
        if self.request.method == 'PATCH' or self.action == 'list':
            return [IsAdminUser()]
        return [AllowAny()]

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

    def partial_update(self, request, *args, **kwargs):
        return_request = self.get_object()
        serializer = ReviewReturnSerializer(
            instance=return_request, data=request.data)
        serializer.is_valid(raise_exception=True)
        return_request = serializer.save()
        return Response(ReturnSerializer(return_request).data)
