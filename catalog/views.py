from django.db.models.aggregates import Count
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
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


@extend_schema_view(
    list=extend_schema(
        summary='Browse products',
        description='List published products. Open to everyone, supports search, filtering, and ordering.'),
    retrieve=extend_schema(
        summary='Get product details',
        description='Retrieve a single product by id. Open to everyone.'),
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


@extend_schema_view(
    list=extend_schema(
        summary='List products (admin)',
        description='List all products, including unpublished ones. Staff-only.'),
    retrieve=extend_schema(
        summary='Get product (admin)',
        description='Retrieve a single product by id. Staff-only.'),
    create=extend_schema(
        summary='Create product',
        description='Create a new product. Staff-only.'),
    update=extend_schema(
        summary='Replace product',
        description='Full update of a product. Staff-only.'),
    partial_update=extend_schema(
        summary='Update product',
        description='Partial update of a product (e.g. toggle availability via status). Staff-only.'),
    destroy=extend_schema(
        summary='Delete product',
        description='Delete a product. Rejected with 405 if the product is associated with an order item. Staff-only.'),
)
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


@extend_schema_view(
    list=extend_schema(
        summary='Browse collections',
        description='List product collections. Open to everyone.'),
    retrieve=extend_schema(
        summary='Get collection details',
        description='Retrieve a single collection by id. Open to everyone.'),
)
class CollectionViewSet(ReadOnlyModelViewSet):
    """store-front/: read-only browsing, open to everyone."""
    queryset = Collection.objects.annotate(
        products_count=Count('products')).all()
    serializer_class = CollectionSerializer
    permission_classes = [AllowAny]


@extend_schema_view(
    list=extend_schema(
        summary='List collections (admin)',
        description='List all collections. Staff-only.'),
    retrieve=extend_schema(
        summary='Get collection (admin)',
        description='Retrieve a single collection by id. Staff-only.'),
    create=extend_schema(
        summary='Create collection',
        description='Create a new collection. Staff-only.'),
    update=extend_schema(
        summary='Replace collection',
        description='Full update of a collection. Staff-only.'),
    partial_update=extend_schema(
        summary='Update collection',
        description='Partial update of a collection. Staff-only.'),
    destroy=extend_schema(
        summary='Delete collection',
        description='Delete a collection. Rejected with 405 if it still includes products. Staff-only.'),
)
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


@extend_schema_view(
    list=extend_schema(
        summary='List product images',
        description="List a product's images. Open to everyone."),
    retrieve=extend_schema(
        summary='Get product image',
        description='Retrieve a single product image by id. Open to everyone.'),
)
class ProductImageViewSet(ReadOnlyModelViewSet):
    """store-front/: read-only, open to everyone."""
    serializer_class = ProductImageSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return ProductImage.objects.filter(product_id=self.kwargs['product_pk'])

    def get_serializer_context(self):
        return {'product_id': self.kwargs['product_pk']}


@extend_schema_view(
    list=extend_schema(
        summary='List product images (admin)',
        description="List a product's images. Staff-only."),
    retrieve=extend_schema(
        summary='Get product image (admin)',
        description='Retrieve a single product image by id. Staff-only.'),
    create=extend_schema(
        summary='Add product image',
        description='Attach a new image to a product. Staff-only.'),
    update=extend_schema(
        summary='Replace product image',
        description='Full update of a product image. Staff-only.'),
    partial_update=extend_schema(
        summary='Update product image',
        description='Partial update of a product image. Staff-only.'),
    destroy=extend_schema(
        summary='Delete product image',
        description='Remove an image from a product. Staff-only.'),
)
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


@extend_schema_view(
    list=extend_schema(
        summary='List product reviews',
        description='List reviews left for a product. Open to everyone.'),
    retrieve=extend_schema(
        summary='Get review',
        description='Retrieve a single review by id. Open to everyone.'),
    create=extend_schema(
        summary='Leave a review',
        description='Post a review for a product. Requires authentication; only customers who purchased the product may post one.'),
    update=extend_schema(
        summary='Replace review',
        description='Full update of your own review. Requires authentication.'),
    partial_update=extend_schema(
        summary='Update review',
        description='Partial update of your own review. Requires authentication.'),
    destroy=extend_schema(
        summary='Delete review',
        description='Delete your own review. Requires authentication.'),
)
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
