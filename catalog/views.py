from django.db import transaction
from django.db.models.aggregates import Count
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework import status
from django.shortcuts import get_object_or_404
from core.pagination import DefaultPagination
from customers.models import Customer
from media_storage.services.upload import delete_image
from .filters import ProductFilter
from .models import Collection, Product, ProductImage, Review, Variant
from .serializers import (
    CollectionSerializer, CreateProductSerializer, ProductImageSerializer,
    ProductListSerializer, ProductSerializer, ReviewSerializer, VariantSerializer,
)


@extend_schema_view(
    list=extend_schema(
        summary='Browse products',
        description='List published products. Open to everyone, supports search, filtering, and ordering.'),
    retrieve=extend_schema(
        summary='Get product details',
        description='Retrieve a single product by slug. Open to everyone.'),
)
class ProductViewSet(ReadOnlyModelViewSet):
    """store-front/: read-only browsing, open to everyone. Looked up by
    slug (not id) — this is the customer-facing surface, admin keeps id."""
    # distinct(): filtering/ordering crosses the Product->Variant relation
    # now (price lives on Variant), which can otherwise duplicate a Product
    # row per matching variant.
    queryset = Product.objects.all().distinct().prefetch_related(
        'images', 'variants__images', 'axes__values__images')
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    pagination_class = DefaultPagination
    permission_classes = [AllowAny]
    search_fields = ['title', 'description']
    ordering_fields = ['variants__unit_price', 'last_update']
    lookup_field = 'slug'

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
        description=(
            'Create a new product. Staff-only. Multipart request: a '
            "'data' part (JSON: name, price {amount, currency}, axes "
            '[{name, sortOrder, allowedValues: [{name, code}]}]) plus an '
            "'images' part with one or more files."),
        request={'multipart/form-data': CreateProductSerializer},
        responses=ProductSerializer),
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
    queryset = Product.objects.all().distinct().prefetch_related(
        'images', 'variants__images', 'axes__values__images')
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    pagination_class = DefaultPagination
    permission_classes = [IsAdminUser]
    search_fields = ['title', 'description']
    ordering_fields = ['variants__unit_price', 'last_update']

    def get_serializer_class(self):
        if self.action == 'create':
            return CreateProductSerializer
        if self.action == 'list':
            # Trimmed shape for the list table — see ProductListSerializer.
            return ProductListSerializer
        return ProductSerializer

    def get_serializer_context(self):
        return {'request': self.request}

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        output = ProductSerializer(product, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)

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
    """store-front/: read-only, open to everyone. Nested under the
    slug-looked-up product (see ProductViewSet) — the nested router names
    the url kwarg 'product_slug' to match, so resolve it to the real
    numeric id before touching the FK."""
    serializer_class = ProductImageSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return ProductImage.objects.filter(product__slug=self.kwargs['product_slug'])

    def get_serializer_context(self):
        product = get_object_or_404(Product, slug=self.kwargs['product_slug'])
        return {'product_id': product.id}


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

    def perform_destroy(self, instance):
        delete_image(instance.image_key)
        instance.delete()


@extend_schema_view(
    list=extend_schema(
        summary='List product variants (admin)',
        description="List a product's variants. Staff-only."),
    retrieve=extend_schema(
        summary='Get product variant (admin)',
        description='Retrieve a single variant by id. Staff-only.'),
    create=extend_schema(
        summary='Add product variant',
        description='Add a new variant (sku/price/inventory) to a product, outside the product create/update payload. Staff-only.'),
    update=extend_schema(
        summary='Replace product variant',
        description='Full update of a product variant. Staff-only.'),
    partial_update=extend_schema(
        summary='Update product variant',
        description='Partial update of a product variant. Staff-only.'),
    destroy=extend_schema(
        summary='Delete product variant',
        description='Delete a product variant. Staff-only.'),
)
class VariantAdminViewSet(ModelViewSet):
    """Manages a product's variants (sku/price/inventory) outside the
    product create/update payload — same admin-only surface as
    ProductImageAdminViewSet."""
    serializer_class = VariantSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return Variant.objects.filter(product_id=self.kwargs['product_pk'])

    def get_serializer_context(self):
        return {'product_id': self.kwargs['product_pk']}

    @extend_schema(
        summary='Batch-add product variants',
        description=(
            'Create multiple variants for a product in one request — a '
            'JSON array, each item shaped like a single-variant create '
            'payload (sku/unit_price/.../axis_value_ids). All-or-nothing: '
            'any invalid entry, or any two entries (in this batch or '
            'against existing variants) sharing sku or axis-value '
            'combination, rejects the whole batch and creates nothing. '
            'Staff-only.'),
        request=VariantSerializer(many=True),
        responses=VariantSerializer(many=True))
    @action(detail=False, methods=['post'])
    def batch(self, request, product_pk=None):
        payload = request.data
        if not isinstance(payload, list) or not payload:
            return Response(
                {'detail': 'Expected a non-empty list of variants.'},
                status=status.HTTP_400_BAD_REQUEST)

        skus = [item.get('sku') if isinstance(item, dict) else None for item in payload]
        dupe_skus = {sku for sku in skus if sku and skus.count(sku) > 1}
        if dupe_skus:
            return Response(
                {'detail': f"Duplicate sku(s) within this batch: {', '.join(sorted(dupe_skus))}."},
                status=status.HTTP_400_BAD_REQUEST)

        context = self.get_serializer_context()
        item_serializers = [VariantSerializer(data=item, context=context) for item in payload]
        field_errors = [None if s.is_valid() else s.errors for s in item_serializers]
        if any(field_errors):
            return Response(field_errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                variants = [s.save() for s in item_serializers]
        except ValidationError as exc:
            # A business-rule check (completeness / no-duplicate-combination)
            # failed on save — same shape of error as the single-create
            # endpoint would give, just for whichever item triggered it.
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            VariantSerializer(variants, many=True, context=context).data,
            status=status.HTTP_201_CREATED)


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
    class is unchanged and lives under store-front/ only. Nested under the
    slug-looked-up product (see ProductViewSet) — the nested router names
    the url kwarg 'product_slug' to match, so resolve to the real id first."""
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return Review.objects.filter(product__slug=self.kwargs['product_slug'])

    def get_serializer_context(self):
        product = get_object_or_404(Product, slug=self.kwargs['product_slug'])
        context = {'product_id': product.id}
        if self.request.user.is_authenticated:
            context['customer'] = Customer.objects.filter(
                user=self.request.user).first()
        return context
