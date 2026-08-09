from django.db.models.aggregates import Count
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework import status
from core.pagination import DefaultPagination
from customers.models import Customer
from .filters import ProductFilter
from .models import Collection, Product, ProductImage, Review
from .serializers import (
    CollectionSerializer, ProductImageSerializer, ProductSerializer,
    ReviewSerializer,
)


class ProductViewSet(ReadOnlyModelViewSet):
    """store-front/: read-only browsing, open to everyone."""
    # distinct(): filtering/ordering crosses the Product->Variant relation
    # now (price lives on Variant), which can otherwise duplicate a Product
    # row per matching variant.
    queryset = Product.objects.all().distinct()
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    pagination_class = DefaultPagination
    permission_classes = [AllowAny]
    search_fields = ['title', 'description']
    ordering_fields = ['variants__unit_price', 'last_update']

    def get_serializer_context(self):
        return {'request': self.request}


class ProductAdminViewSet(ModelViewSet):
    """store-admin/: full CRUD, staff-only."""
    queryset = Product.objects.all().distinct()
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    pagination_class = DefaultPagination
    permission_classes = [IsAdminUser]
    search_fields = ['title', 'description']
    ordering_fields = ['variants__unit_price', 'last_update']

    def get_serializer_context(self):
        return {'request': self.request}

    def destroy(self, request, *args, **kwargs):
        if Product.objects.filter(
                pk=kwargs['pk'], variants__orderitems__isnull=False).exists():
            return Response({'error': 'Product cannot be deleted because it is associated with an order item.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

        return super().destroy(request, *args, **kwargs)


class CollectionViewSet(ReadOnlyModelViewSet):
    """store-front/: read-only browsing, open to everyone."""
    queryset = Collection.objects.annotate(
        products_count=Count('products')).all()
    serializer_class = CollectionSerializer
    permission_classes = [AllowAny]


class CollectionAdminViewSet(ModelViewSet):
    """store-admin/: full CRUD, staff-only."""
    queryset = Collection.objects.annotate(
        products_count=Count('products')).all()
    serializer_class = CollectionSerializer
    permission_classes = [IsAdminUser]

    def destroy(self, request, *args, **kwargs):
        if Product.objects.filter(collection_id=kwargs['pk']):
            return Response({'error': 'Collection cannot be deleted because it includes one or more products.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

        return super().destroy(request, *args, **kwargs)


class ProductImageViewSet(ReadOnlyModelViewSet):
    """store-front/: read-only, open to everyone."""
    serializer_class = ProductImageSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return ProductImage.objects.filter(product_id=self.kwargs['product_pk'])

    def get_serializer_context(self):
        return {'product_id': self.kwargs['product_pk']}


class ProductImageAdminViewSet(ModelViewSet):
    """Attaches images to a product (US-20): admin-scoped, same as the
    product write endpoints (Business Rule: 'Only Admin can change product
    availability' — images are part of that same admin-only surface)."""
    serializer_class = ProductImageSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return ProductImage.objects.filter(product_id=self.kwargs['product_pk'])

    def get_serializer_context(self):
        return {'product_id': self.kwargs['product_pk']}


class ReviewViewSet(ModelViewSet):
    """US-19: reviews are public to read, but only a customer who has
    actually purchased the product may post one (enforced in
    ReviewSerializer.validate). No admin-only action exists today — this
    class is unchanged and lives under store-front/ only."""
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return Review.objects.filter(product_id=self.kwargs['product_pk'])

    def get_serializer_context(self):
        context = {'product_id': self.kwargs['product_pk']}
        if self.request.user.is_authenticated:
            context['customer'] = Customer.objects.filter(
                user=self.request.user).first()
        return context
