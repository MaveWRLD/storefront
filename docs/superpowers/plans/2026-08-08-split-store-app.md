# Split `store` App Into `catalog`, `cart`, `customers`, `orders` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the monolithic `store` Django app with four focused apps —
`catalog`, `cart`, `customers`, `orders` — with no change to the public API
URL surface.

**Architecture:** Pure structural refactor. Models/serializers/views/admin
move to the app that owns their bounded context. Cross-app foreign keys use
Django's lazy `'app_label.Model'` string form. Shared, non-domain-specific
DRF permission/pagination classes move into the existing `core` app. All four
new apps' URLs stay mounted under the existing `store/` prefix so no API
client sees a path change.

**Tech Stack:** Django 6.1, Django REST Framework, `django-filter`,
`drf-nested-routers`, PostgreSQL (dev DB, no data to preserve).

## Global Constraints

- API URL prefix `store/` must be unchanged (spec: "Keep API paths
  identical").
- Cross-app FKs use string form `'app_label.Model'`, not direct class import
  (spec: approved FK style).
- Fresh `0001_initial.py` migration per new app — no history-preserving
  migration tricks (spec: approved migration approach, dev DB only).
- `likes`, `tags`, `playground` are out of scope — do not touch them.
- No new test coverage is being added; existing tests must keep passing.

---

## Task 1: Create `catalog` app (Product, Collection, Promotion, Review)

**Files:**
- Create: `catalog/__init__.py`, `catalog/apps.py`, `catalog/models.py`,
  `catalog/admin.py`, `catalog/filters.py`, `catalog/validators.py`,
  `catalog/serializers.py`, `catalog/views.py`, `catalog/urls.py`,
  `catalog/migrations/__init__.py`, `catalog/tests/__init__.py`,
  `catalog/tests/test_collections.py`,
  `catalog/management/__init__.py`,
  `catalog/management/commands/__init__.py`,
  `catalog/management/commands/seed_db.py`,
  `catalog/management/commands/seed.sql`
- Delete (moved from): `store/tests/test_collections.py`,
  `store/management/commands/seed_db.py`, `store/management/commands/seed.sql`

**Interfaces:**
- Produces: `catalog.models.Product`, `catalog.models.Collection`,
  `catalog.models.Promotion`, `catalog.models.Review`;
  `catalog.serializers.SimpleProductSerializer` (consumed later by `cart`
  and `orders` serializers); `catalog.admin.ProductAdmin` (consumed later by
  `core/admin.py`).

- [ ] **Step 1: Scaffold the app**

```bash
python manage.py startapp catalog
rm catalog/tests.py catalog/models.py
mkdir catalog/tests catalog/management catalog/management/commands
touch catalog/tests/__init__.py catalog/management/__init__.py catalog/management/commands/__init__.py
```

- [ ] **Step 2: Write `catalog/models.py`**

```python
from django.db import models
from django.core.validators import MinValueValidator


class Promotion(models.Model):
    description = models.CharField(max_length=255)
    discount = models.FloatField()


class Collection(models.Model):
    title = models.CharField(max_length=255)
    featured_product = models.ForeignKey(
        'Product', on_delete=models.SET_NULL, null=True, related_name='+', blank=True)

    def __str__(self) -> str:
        return self.title

    class Meta:
        ordering = ['title']


class Product(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField()
    description = models.TextField(null=True, blank=True)
    unit_price = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(1)])
    inventory = models.IntegerField(validators=[MinValueValidator(0)])
    last_update = models.DateTimeField(auto_now=True)
    collection = models.ForeignKey(
        Collection, on_delete=models.PROTECT, related_name='products')
    promotions = models.ManyToManyField(Promotion, blank=True)

    def __str__(self) -> str:
        return self.title

    class Meta:
        ordering = ['title']


class Review(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='reviews')
    name = models.CharField(max_length=255)
    description = models.TextField()
    date = models.DateField(auto_now_add=True)
```

- [ ] **Step 3: Write `catalog/filters.py`**

```python
from django_filters.rest_framework import FilterSet
from .models import Product


class ProductFilter(FilterSet):
    class Meta:
        model = Product
        fields = {
            'collection_id': ['exact'],
            'unit_price': ['gt', 'lt']
        }
```

- [ ] **Step 4: Write `catalog/validators.py`**

```python
from django.core.exceptions import ValidationError


def validate_file_size(file):
    max_size_kb = 50

    if file.size > max_size_kb * 1024:
        raise ValidationError(f'File size cannot be greater tha {max_size_kb}kb')
```

- [ ] **Step 5: Write `catalog/serializers.py`**

```python
from decimal import Decimal
from rest_framework import serializers
from .models import Product, Collection, Review


class CollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collection
        fields = ['id', 'title', 'products_count']

    products_count = serializers.IntegerField(read_only=True)


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'title', 'description', 'slug', 'inventory',
                  'unit_price', 'price_with_tax', 'collection']

    price_with_tax = serializers.SerializerMethodField(
        method_name='calculate_tax')

    def calculate_tax(self, product: Product):
        return product.unit_price * Decimal(1.1)


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['id', 'date', 'name', 'description']

    def create(self, validated_data):
        product_id = self.context['product_id']
        return Review.objects.create(product_id=product_id, **validated_data)


class SimpleProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'title', 'unit_price']
```

- [ ] **Step 6: Write `catalog/views.py`**

```python
from django.db.models.aggregates import Count
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework import status
from core.pagination import DefaultPagination
from core.permissions import IsAdminOrReadOnly
from orders.models import OrderItem
from .filters import ProductFilter
from .models import Collection, Product, Review
from .serializers import CollectionSerializer, ProductSerializer, ReviewSerializer


class ProductViewSet(ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ProductFilter
    pagination_class = DefaultPagination
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ['title', 'description']
    ordering_fields = ['unit_price', 'last_update']

    def get_serializer_context(self):
        return {'request': self.request}

    def destroy(self, request, *args, **kwargs):
        if OrderItem.objects.filter(product_id=kwargs['pk']).count() > 0:
            return Response({'error': 'Product cannot be deleted because it is associated with an order item.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

        return super().destroy(request, *args, **kwargs)


class CollectionViewSet(ModelViewSet):
    queryset = Collection.objects.annotate(
        products_count=Count('products')).all()
    serializer_class = CollectionSerializer
    permission_classes = [IsAdminOrReadOnly]

    def destroy(self, request, *args, **kwargs):
        if Product.objects.filter(collection_id=kwargs['pk']):
            return Response({'error': 'Collection cannot be deleted because it includes one or more products.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

        return super().destroy(request, *args, **kwargs)


class ReviewViewSet(ModelViewSet):
    serializer_class = ReviewSerializer

    def get_queryset(self):
        return Review.objects.filter(product_id=self.kwargs['product_pk'])

    def get_serializer_context(self):
        return {'product_id': self.kwargs['product_pk']}
```

> Note: `catalog/views.py` imports `orders.models.OrderItem`. This creates a
> reverse edge (`catalog` → `orders`) purely for the destroy-guard check.
> This is acceptable and intentional — Django resolves import-time
> circular risk here because `orders` does not import `catalog.views` (only
> `catalog.models`/`catalog.serializers`), so there is no circular *import*,
> only a circular *conceptual* dependency, which is inherent to the
> "can't delete a product referenced by an order" business rule.

- [ ] **Step 7: Write `catalog/admin.py`**

```python
from django.contrib import admin, messages
from django.db.models.aggregates import Count
from django.db.models.query import QuerySet
from django.utils.html import format_html, urlencode
from django.urls import reverse
from . import models


class InventoryFilter(admin.SimpleListFilter):
    title = 'inventory'
    parameter_name = 'inventory'

    def lookups(self, request, model_admin):
        return [
            ('<10', 'Low')
        ]

    def queryset(self, request, queryset: QuerySet):
        if self.value() == '<10':
            return queryset.filter(inventory__lt=10)


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    autocomplete_fields = ['collection']
    prepopulated_fields = {
        'slug': ['title']
    }
    actions = ['clear_inventory']
    list_display = ['title', 'unit_price',
                    'inventory_status', 'collection_title']
    list_editable = ['unit_price']
    list_filter = ['collection', 'last_update', InventoryFilter]
    list_per_page = 10
    list_select_related = ['collection']
    search_fields = ['title']

    def collection_title(self, product):
        return product.collection.title

    @admin.display(ordering='inventory')
    def inventory_status(self, product):
        if product.inventory < 10:
            return 'Low'
        return 'OK'

    @admin.action(description='Clear inventory')
    def clear_inventory(self, request, queryset):
        updated_count = queryset.update(inventory=0)
        self.message_user(
            request,
            f'{updated_count} products were successfully updated.',
            messages.ERROR
        )


@admin.register(models.Collection)
class CollectionAdmin(admin.ModelAdmin):
    autocomplete_fields = ['featured_product']
    list_display = ['title', 'products_count']
    search_fields = ['title']

    @admin.display(ordering='products_count')
    def products_count(self, collection):
        url = (
            reverse('admin:catalog_product_changelist')
            + '?'
            + urlencode({
                'collection__id': str(collection.id)
            }))
        return format_html('<a href="{}">{} Products</a>', url, collection.products_count)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            products_count=Count('products')
        )
```

> Note the `reverse()` call target changed from `'admin:store_product_changelist'`
> to `'admin:catalog_product_changelist'` — Django admin URL names are
> `admin:<app_label>_<model>_changelist`, so this must track the app rename.

- [ ] **Step 8: Write `catalog/urls.py`**

```python
from rest_framework_nested import routers
from . import views

router = routers.DefaultRouter()
router.register('products', views.ProductViewSet, basename='products')
router.register('collections', views.CollectionViewSet)

products_router = routers.NestedDefaultRouter(
    router, 'products', lookup='product')
products_router.register('reviews', views.ReviewViewSet,
                         basename='product-reviews')

urlpatterns = router.urls + products_router.urls
```

- [ ] **Step 9: Write `catalog/apps.py`**

```python
from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'catalog'
```

- [ ] **Step 10: Move the test file**

```bash
git mv store/tests/test_collections.py catalog/tests/test_collections.py
```

Contents stay as-is (`from django.test import TestCase` placeholder test —
verify by opening the file that it makes no reference to `store`-specific
imports before moving; it currently doesn't).

- [ ] **Step 11: Move the seed command, updating table names**

```bash
git mv store/management/commands/seed_db.py catalog/management/commands/seed_db.py
git mv store/management/commands/seed.sql catalog/management/commands/seed.sql
```

`catalog/management/commands/seed_db.py` needs no code changes (it just
executes whatever SQL is in `seed.sql` next to it).

In `catalog/management/commands/seed.sql`, replace every occurrence of the
old table names with the new ones (Django names tables `<app_label>_<model>`
lowercased):

```bash
sed -i 's/store_collection/catalog_collection/g; s/store_product/catalog_product/g' catalog/management/commands/seed.sql
```

Verify no `store_` prefix remains:

```bash
grep -c "store_" catalog/management/commands/seed.sql
```
Expected: `0`

- [ ] **Step 12: Register the app in settings (temporarily alongside `store`)**

In `storefront/settings.py`, add `'catalog'` to `INSTALLED_APPS` (leave
`'store'` in place for now — it's removed in Task 8 once nothing depends on
it):

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.sessions',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_filters',
    'rest_framework',
    'djoser',
    'playground',
    'debug_toolbar',
    'catalog',
    'store',
    'tags',
    'likes',
    'core',
]
```

- [ ] **Step 13: Verify the app loads (Django system check)**

Run: `python manage.py check catalog`
Expected: no errors related to `catalog` (errors about `orders` not existing
yet are expected and will be resolved in Task 4 — if `check catalog` fails
because `orders` doesn't exist yet, that's fine at this point; full `check`
happens after Task 4).

- [ ] **Step 14: Commit**

```bash
git add catalog/
git add storefront/settings.py
git rm store/tests/test_collections.py store/management/commands/seed_db.py store/management/commands/seed.sql
git commit -m "feat: extract catalog app from store (Product, Collection, Promotion, Review)"
```

---

## Task 2: Create `customers` app (Customer, Address)

**Files:**
- Create: `customers/__init__.py`, `customers/apps.py`,
  `customers/models.py`, `customers/admin.py`, `customers/permissions.py`,
  `customers/serializers.py`, `customers/views.py`, `customers/urls.py`,
  `customers/migrations/__init__.py`, `customers/signals/__init__.py`,
  `customers/signals/handlers.py`

**Interfaces:**
- Produces: `customers.models.Customer`, `customers.models.Address`,
  `customers.serializers.CustomerSerializer` (consumed later by `core`
  via `orders`' checkout flow does not need it, but `core/serializers.py`
  needs `customers.models.Customer`).

- [ ] **Step 1: Scaffold the app**

```bash
python manage.py startapp customers
rm customers/tests.py customers/models.py
mkdir customers/signals
touch customers/signals/__init__.py
```

- [ ] **Step 2: Write `customers/models.py`**

```python
from django.contrib import admin
from django.conf import settings
from django.db import models


class Customer(models.Model):
    MEMBERSHIP_BRONZE = 'B'
    MEMBERSHIP_SILVER = 'S'
    MEMBERSHIP_GOLD = 'G'

    MEMBERSHIP_CHOICES = [
        (MEMBERSHIP_BRONZE, 'Bronze'),
        (MEMBERSHIP_SILVER, 'Silver'),
        (MEMBERSHIP_GOLD, 'Gold'),
    ]
    phone = models.CharField(max_length=255)
    birth_date = models.DateField(null=True, blank=True)
    membership = models.CharField(
        max_length=1, choices=MEMBERSHIP_CHOICES, default=MEMBERSHIP_BRONZE)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'

    @admin.display(ordering='user__first_name')
    def first_name(self):
        return self.user.first_name

    @admin.display(ordering='user__last_name')
    def last_name(self):
        return self.user.last_name

    class Meta:
        ordering = ['user__first_name', 'user__last_name']
        permissions = [
            ('view_history', 'Can view history')
        ]


class Address(models.Model):
    street = models.CharField(max_length=255)
    city = models.CharField(max_length=255)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE)
```

- [ ] **Step 3: Write `customers/permissions.py`**

```python
from rest_framework import permissions


class ViewCustomerHistoryPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.has_perm('customers.view_history')
```

> Note: the permission string changes from `'store.view_history'` to
> `'customers.view_history'` because Django auto-generated permissions are
> namespaced `<app_label>.<codename>`, and `view_history` now belongs to the
> `customers` app.

- [ ] **Step 4: Write `customers/serializers.py`**

```python
from rest_framework import serializers
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Customer
        fields = ['id', 'user_id', 'phone', 'birth_date', 'membership']
```

- [ ] **Step 5: Write `customers/views.py`**

```python
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from .models import Customer
from .permissions import ViewCustomerHistoryPermission
from .serializers import CustomerSerializer


class CustomerViewSet(ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAdminUser]

    @action(detail=True, permission_classes=[ViewCustomerHistoryPermission])
    def history(self, request, pk):
        return Response('ok')

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
```

- [ ] **Step 6: Write `customers/admin.py`**

```python
from django.contrib import admin
from django.db.models.aggregates import Count
from django.utils.html import format_html, urlencode
from django.urls import reverse
from . import models


@admin.register(models.Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name',  'membership', 'orders']
    list_editable = ['membership']
    list_per_page = 10
    list_select_related = ['user']
    ordering = ['user__first_name', 'user__last_name']
    search_fields = ['first_name__istartswith', 'last_name__istartswith']

    @admin.display(ordering='orders_count')
    def orders(self, customer):
        url = (
            reverse('admin:orders_order_changelist')
            + '?'
            + urlencode({
                'customer__id': str(customer.id)
            }))
        return format_html('<a href="{}">{} Orders</a>', url, customer.orders_count)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            orders_count=Count('order')
        )
```

> `reverse()` target changes to `'admin:orders_order_changelist'` — same
> reasoning as `catalog/admin.py`'s change in Task 1.

- [ ] **Step 7: Write `customers/urls.py`**

```python
from rest_framework_nested import routers
from . import views

router = routers.DefaultRouter()
router.register('customers', views.CustomerViewSet)

urlpatterns = router.urls
```

- [ ] **Step 8: Write `customers/signals/handlers.py`**

```python
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from customers.models import Customer


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_customer_for_new_user(sender, **kwargs):
    if kwargs['created']:
        Customer.objects.create(user=kwargs['instance'])
```

- [ ] **Step 9: Write `customers/apps.py`**

```python
from django.apps import AppConfig


class CustomersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'customers'

    def ready(self) -> None:
        import customers.signals.handlers
```

- [ ] **Step 10: Register the app in settings**

Add `'customers'` to `INSTALLED_APPS` in `storefront/settings.py`, right
after `'catalog'`.

- [ ] **Step 11: Verify the app loads**

Run: `python manage.py check customers`
Expected: no errors related to `customers`.

- [ ] **Step 12: Commit**

```bash
git add customers/ storefront/settings.py
git commit -m "feat: extract customers app from store (Customer, Address)"
```

---

## Task 3: Create `cart` app (Cart, CartItem) — depends on `catalog`

**Files:**
- Create: `cart/__init__.py`, `cart/apps.py`, `cart/models.py`,
  `cart/serializers.py`, `cart/views.py`, `cart/urls.py`,
  `cart/migrations/__init__.py`

**Interfaces:**
- Consumes: `catalog.models.Product` (as `'catalog.Product'` string FK
  target), `catalog.serializers.SimpleProductSerializer`.
- Produces: `cart.models.Cart`, `cart.models.CartItem` (consumed later by
  `orders.serializers.CreateOrderSerializer`).

- [ ] **Step 1: Scaffold the app**

```bash
python manage.py startapp cart
rm cart/tests.py cart/admin.py cart/models.py
```

(`cart` has no admin registrations in the current `store/admin.py`, so
`cart/admin.py` is deleted rather than populated.)

- [ ] **Step 2: Write `cart/models.py`**

```python
from django.core.validators import MinValueValidator
from django.db import models
from uuid import uuid4


class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    created_at = models.DateTimeField(auto_now_add=True)


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('catalog.Product', on_delete=models.CASCADE)
    quantity = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)]
    )

    class Meta:
        unique_together = [['cart', 'product']]
```

- [ ] **Step 3: Write `cart/serializers.py`**

```python
from rest_framework import serializers
from catalog.models import Product
from catalog.serializers import SimpleProductSerializer
from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product = SimpleProductSerializer()
    total_price = serializers.SerializerMethodField()

    def get_total_price(self, cart_item: CartItem):
        return cart_item.quantity * cart_item.product.unit_price

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'quantity', 'total_price']


class CartSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    items = CartItemSerializer(many=True, read_only=True)
    total_price = serializers.SerializerMethodField()

    def get_total_price(self, cart):
        return sum([item.quantity * item.product.unit_price for item in cart.items.all()])

    class Meta:
        model = Cart
        fields = ['id', 'items', 'total_price']


class AddCartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField()

    def validate_product_id(self, value):
        if not Product.objects.filter(pk=value).exists():
            raise serializers.ValidationError(
                'No product with the given ID was found.')
        return value

    def save(self, **kwargs):
        cart_id = self.context['cart_id']
        product_id = self.validated_data['product_id']
        quantity = self.validated_data['quantity']

        try:
            cart_item = CartItem.objects.get(
                cart_id=cart_id, product_id=product_id)
            cart_item.quantity += quantity
            cart_item.save()
            self.instance = cart_item
        except CartItem.DoesNotExist:
            self.instance = CartItem.objects.create(
                cart_id=cart_id, **self.validated_data)

        return self.instance

    class Meta:
        model = CartItem
        fields = ['id', 'product_id', 'quantity']


class UpdateCartItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = ['quantity']
```

- [ ] **Step 4: Write `cart/views.py`**

```python
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin, RetrieveModelMixin
from rest_framework.viewsets import ModelViewSet, GenericViewSet
from .models import Cart, CartItem
from .serializers import AddCartItemSerializer, CartItemSerializer, CartSerializer, UpdateCartItemSerializer


class CartViewSet(CreateModelMixin,
                  RetrieveModelMixin,
                  DestroyModelMixin,
                  GenericViewSet):
    queryset = Cart.objects.prefetch_related('items__product').all()
    serializer_class = CartSerializer


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
            .select_related('product')
```

- [ ] **Step 5: Write `cart/urls.py`**

```python
from rest_framework_nested import routers
from . import views

router = routers.DefaultRouter()
router.register('carts', views.CartViewSet)

carts_router = routers.NestedDefaultRouter(router, 'carts', lookup='cart')
carts_router.register('items', views.CartItemViewSet, basename='cart-items')

urlpatterns = router.urls + carts_router.urls
```

- [ ] **Step 6: Write `cart/apps.py`**

```python
from django.apps import AppConfig


class CartConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cart'
```

- [ ] **Step 7: Register the app in settings**

Add `'cart'` to `INSTALLED_APPS` in `storefront/settings.py`, right after
`'customers'`.

- [ ] **Step 8: Verify the app loads**

Run: `python manage.py check cart`
Expected: no errors related to `cart`.

- [ ] **Step 9: Commit**

```bash
git add cart/ storefront/settings.py
git commit -m "feat: extract cart app from store (Cart, CartItem)"
```

---

## Task 4: Create `orders` app (Order, OrderItem) — depends on `catalog`, `customers`, `cart`

**Files:**
- Create: `orders/__init__.py`, `orders/apps.py`, `orders/models.py`,
  `orders/admin.py`, `orders/serializers.py`, `orders/views.py`,
  `orders/urls.py`, `orders/urls.py`, `orders/migrations/__init__.py`,
  `orders/signals/__init__.py`

**Interfaces:**
- Consumes: `catalog.models.Product` (`'catalog.Product'` string FK),
  `catalog.serializers.SimpleProductSerializer`,
  `customers.models.Customer` (`'customers.Customer'` string FK),
  `cart.models.Cart`, `cart.models.CartItem`.
- Produces: `orders.models.Order`, `orders.models.OrderItem`,
  `orders.signals.order_created` (consumed later by
  `core/signals/handlers.py`).

- [ ] **Step 1: Scaffold the app**

```bash
python manage.py startapp orders
rm orders/tests.py orders/models.py
mkdir orders/signals
```

- [ ] **Step 2: Write `orders/models.py`**

```python
from django.db import models


class Order(models.Model):
    PAYMENT_STATUS_PENDING = 'P'
    PAYMENT_STATUS_COMPLETE = 'C'
    PAYMENT_STATUS_FAILED = 'F'
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_STATUS_PENDING, 'Pending'),
        (PAYMENT_STATUS_COMPLETE, 'Complete'),
        (PAYMENT_STATUS_FAILED, 'Failed')
    ]

    placed_at = models.DateTimeField(auto_now_add=True)
    payment_status = models.CharField(
        max_length=1, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_STATUS_PENDING)
    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT)

    class Meta:
        permissions = [
            ('cancel_order', 'Can cancel order')
        ]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='items')
    product = models.ForeignKey(
        'catalog.Product', on_delete=models.PROTECT, related_name='orderitems')
    quantity = models.PositiveSmallIntegerField()
    unit_price = models.DecimalField(max_digits=6, decimal_places=2)
```

- [ ] **Step 3: Write `orders/signals/__init__.py`**

```python
from django.dispatch import Signal

order_created = Signal()
```

- [ ] **Step 4: Write `orders/serializers.py`**

```python
from django.db import transaction
from rest_framework import serializers
from cart.models import Cart, CartItem
from catalog.serializers import SimpleProductSerializer
from customers.models import Customer
from .models import Order, OrderItem
from .signals import order_created


class OrderItemSerializer(serializers.ModelSerializer):
    product = SimpleProductSerializer()

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'unit_price', 'quantity']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = ['id', 'customer', 'placed_at', 'payment_status', 'items']


class UpdateOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['payment_status']


class CreateOrderSerializer(serializers.Serializer):
    cart_id = serializers.UUIDField()

    def validate_cart_id(self, cart_id):
        if not Cart.objects.filter(pk=cart_id).exists():
            raise serializers.ValidationError(
                'No cart with the given ID was found.')
        if CartItem.objects.filter(cart_id=cart_id).count() == 0:
            raise serializers.ValidationError('The cart is empty.')
        return cart_id

    def save(self, **kwargs):
        with transaction.atomic():
            cart_id = self.validated_data['cart_id']

            customer = Customer.objects.get(
                user_id=self.context['user_id'])
            order = Order.objects.create(customer=customer)

            cart_items = CartItem.objects \
                .select_related('product') \
                .filter(cart_id=cart_id)
            order_items = [
                OrderItem(
                    order=order,
                    product=item.product,
                    unit_price=item.product.unit_price,
                    quantity=item.quantity
                ) for item in cart_items
            ]
            OrderItem.objects.bulk_create(order_items)

            Cart.objects.filter(pk=cart_id).delete()

            order_created.send_robust(self.__class__, order=order)

            return order
```

- [ ] **Step 5: Write `orders/views.py`**

```python
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from customers.models import Customer
from .models import Order
from .serializers import CreateOrderSerializer, OrderSerializer, UpdateOrderSerializer


class OrderViewSet(ModelViewSet):
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        if self.request.method in ['PATCH', 'DELETE']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = CreateOrderSerializer(
            data=request.data,
            context={'user_id': self.request.user.id})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        serializer = OrderSerializer(order)
        return Response(serializer.data)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CreateOrderSerializer
        elif self.request.method == 'PATCH':
            return UpdateOrderSerializer
        return OrderSerializer

    def get_queryset(self):
        user = self.request.user

        if user.is_staff:
            return Order.objects.all()

        customer_id = Customer.objects.only(
            'id').get(user_id=user.id)
        return Order.objects.filter(customer_id=customer_id)
```

- [ ] **Step 6: Write `orders/admin.py`**

```python
from django.contrib import admin
from . import models


class OrderItemInline(admin.TabularInline):
    autocomplete_fields = ['product']
    min_num = 1
    max_num = 10
    model = models.OrderItem
    extra = 0


@admin.register(models.Order)
class OrderAdmin(admin.ModelAdmin):
    autocomplete_fields = ['customer']
    inlines = [OrderItemInline]
    list_display = ['id', 'placed_at', 'customer']
```

- [ ] **Step 7: Write `orders/urls.py`**

```python
from rest_framework_nested import routers
from . import views

router = routers.DefaultRouter()
router.register('orders', views.OrderViewSet, basename='orders')

urlpatterns = router.urls
```

- [ ] **Step 8: Write `orders/apps.py`**

```python
from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'orders'
```

- [ ] **Step 9: Register the app in settings**

Add `'orders'` to `INSTALLED_APPS` in `storefront/settings.py`, right after
`'cart'`.

- [ ] **Step 10: Verify the app loads**

Run: `python manage.py check orders`
Expected: no errors related to `orders`.

Now also re-run the full check, since `catalog/views.py` (Task 1) imports
`orders.models.OrderItem`, which only now exists:

Run: `python manage.py check`
Expected: no errors from `catalog`, `customers`, `cart`, or `orders` (errors
from `store` still existing alongside them are expected and resolved in
Task 8).

- [ ] **Step 11: Commit**

```bash
git add orders/ storefront/settings.py
git commit -m "feat: extract orders app from store (Order, OrderItem)"
```

---

## Task 5: Move shared pagination/permissions into `core`

**Files:**
- Create: `core/pagination.py`, `core/permissions.py`
- Modify: `catalog/views.py:1-9` (already written to import from `core` in
  Task 1 — this task adds the files those imports point to)

**Interfaces:**
- Produces: `core.pagination.DefaultPagination`,
  `core.permissions.IsAdminOrReadOnly`,
  `core.permissions.FullDjangoModelPermissions`.

- [ ] **Step 1: Write `core/pagination.py`**

```python
from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    page_size = 10
```

- [ ] **Step 2: Write `core/permissions.py`**

```python
from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


class FullDjangoModelPermissions(permissions.DjangoModelPermissions):
    def __init__(self) -> None:
        self.perms_map['GET'] = ['%(app_label)s.view_%(model_name)s']
```

- [ ] **Step 3: Verify `catalog` resolves its `core` imports**

Run: `python manage.py check catalog`
Expected: no import errors (Task 1's `catalog/views.py` already references
`core.pagination.DefaultPagination` and `core.permissions.IsAdminOrReadOnly`
— this step confirms those now resolve).

- [ ] **Step 4: Commit**

```bash
git add core/pagination.py core/permissions.py
git commit -m "feat: move shared pagination/permission classes into core"
```

---

## Task 6: Update `core`'s cross-app references

**Files:**
- Modify: `core/admin.py`, `core/serializers.py`,
  `core/signals/handlers.py`

**Interfaces:**
- Consumes: `catalog.models.Product`, `catalog.admin.ProductAdmin`,
  `customers.models.Customer`, `orders.signals.order_created`.

- [ ] **Step 1: Update `core/admin.py`**

Read the current file first, then replace its imports:

```python
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.contenttypes.admin import GenericTabularInline
from catalog.models import Product
from catalog.admin import ProductAdmin
from tags.models import TaggedItem
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'email', 'first_name', 'last_name'),
        }),
    )

class TagInline(GenericTabularInline):
    autocomplete_fields = ['tag']
    model = TaggedItem


class CustomProductAdmin(ProductAdmin):
    inlines = [TagInline]


admin.site.unregister(Product)
admin.site.register(Product, CustomProductAdmin)
```

(Only the import lines change — `from store.models import Product` →
`from catalog.models import Product`, `from store.admin import ProductAdmin`
→ `from catalog.admin import ProductAdmin`.)

- [ ] **Step 2: Update `core/serializers.py`**

```python
from customers.models import Customer
from djoser.serializers import UserSerializer as BaseUserSerializer, UserCreateSerializer as BaseUserCreateSerializer


class UserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        fields = ['id', 'username', 'password',
                  'email', 'first_name', 'last_name']


class UserSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
```

(Only `from store.models import Customer` → `from customers.models import
Customer` changes; note `Customer` isn't even referenced elsewhere in this
file today — it's an existing unused import, left as-is since removing it is
out of scope for this refactor.)

- [ ] **Step 3: Update `core/signals/handlers.py`**

```python
from django.dispatch import receiver
from orders.signals import order_created


@receiver(order_created)
def on_order_created(sender, **kwargs):
    print(kwargs['order'])
```

(Only `from store.signals import order_created` → `from orders.signals
import order_created` changes.)

- [ ] **Step 4: Verify**

Run: `python manage.py check core`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add core/admin.py core/serializers.py core/signals/handlers.py
git commit -m "refactor: point core's cross-app imports at catalog/customers/orders"
```

---

## Task 7: Wire up `storefront` settings and URLs

**Files:**
- Modify: `storefront/settings.py` (`INSTALLED_APPS`)
- Modify: `storefront/urls.py`

**Interfaces:**
- Consumes: `catalog.urls`, `cart.urls`, `customers.urls`, `orders.urls`.

- [ ] **Step 1: Finalize `INSTALLED_APPS` in `storefront/settings.py`**

Remove `'store'` from the list (Tasks 1–4 already added the four new apps
alongside it):

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.sessions',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_filters',
    'rest_framework',
    'djoser',
    'playground',
    'debug_toolbar',
    'catalog',
    'customers',
    'cart',
    'orders',
    'tags',
    'likes',
    'core',
]
```

- [ ] **Step 2: Update `storefront/urls.py`**

```python
"""storefront URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
import debug_toolbar

admin.site.site_header = 'Storefront Admin'
admin.site.index_title = 'Admin'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('playground/', include('playground.urls')),
    path('store/', include('catalog.urls')),
    path('store/', include('cart.urls')),
    path('store/', include('customers.urls')),
    path('store/', include('orders.urls')),
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.jwt')),
    path('__debug__/', include(debug_toolbar.urls)),
]
```

- [ ] **Step 3: Verify URL resolution**

Run: `python manage.py show_urls 2>/dev/null | grep store/ || python manage.py check`

(If `show_urls` isn't installed, `python manage.py check` at minimum must
pass with no URL-resolution errors; a fuller manual check happens in Task 8
step 4 once the DB is migrated.)

- [ ] **Step 4: Commit**

```bash
git add storefront/settings.py storefront/urls.py
git commit -m "refactor: mount catalog/cart/customers/orders under the store/ URL prefix"
```

---

## Task 8: Delete `store`, generate fresh migrations, verify end-to-end

**Files:**
- Delete: `store/` (entire directory)
- Create: `catalog/migrations/0001_initial.py`,
  `cart/migrations/0001_initial.py`,
  `customers/migrations/0001_initial.py`,
  `orders/migrations/0001_initial.py`

**Interfaces:** None new — this is the integration/verification task.

- [ ] **Step 1: Remove `store` from `INSTALLED_APPS` (already done in Task 7)
  and delete the app directory**

```bash
git rm -r store/
```

- [ ] **Step 2: Generate fresh migrations for the four new apps**

```bash
python manage.py makemigrations catalog customers cart orders
```

Expected: Django creates one `0001_initial.py` per app. Inspect each to
confirm:
- `catalog/migrations/0001_initial.py` creates `Promotion`, `Collection`,
  `Product` (with the `featured_product` FK added via a second
  `AddField`/circular-dependency-safe operation, same as the original
  `store` migration did), `Review`.
- `customers/migrations/0001_initial.py` creates `Customer`, `Address`.
- `cart/migrations/0001_initial.py` creates `Cart`, `CartItem`, and its
  `CartItem.product` FK migration dependency references `catalog`'s
  migration.
- `orders/migrations/0001_initial.py` creates `Order`, `OrderItem`, and its
  migration dependencies reference both `catalog`'s and `customers`'
  migrations.

- [ ] **Step 3: Reset the dev database and migrate from zero**

```bash
python manage.py migrate
```

If the dev Postgres DB already has the old `store_*` tables from a previous
run, drop and recreate the `storefront` database first (dev-only, no data
to preserve, per spec):

```bash
psql -h localhost -p 5433 -U postgres -c "DROP DATABASE IF EXISTS storefront;"
psql -h localhost -p 5433 -U postgres -c "CREATE DATABASE storefront;"
python manage.py migrate
```

Expected: all migrations apply cleanly with no errors.

- [ ] **Step 4: Run the full test suite**

```bash
python manage.py test
```

Expected: all tests pass, including `catalog.tests.test_collections`.

- [ ] **Step 5: Run the full system check**

```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 6: Manually verify key endpoints resolve**

Start the dev server and confirm each URL resolves to the right view (a
401/403 response is fine — it proves routing works; a 404 is not):

```bash
python manage.py runserver &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/store/products/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/store/collections/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/store/carts/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/store/customers/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/store/orders/
kill %1
```

Expected: `products/` and `collections/` return `200` (public read); `carts/`
returns `200` or `405` (no GET-list by design — only create/retrieve/destroy
mixins); `customers/` and `orders/` return `403` (auth required) — none
return `404`.

- [ ] **Step 7: Seed the database to sanity-check the moved management command**

```bash
python manage.py seed_db
```

Expected: `Populating the database...` printed, no SQL errors (confirms the
`catalog_collection`/`catalog_product` table name rewrite in Task 1 Step 11
was correct).

- [ ] **Step 8: Final commit**

```bash
git add catalog/migrations customers/migrations cart/migrations orders/migrations
git commit -m "chore: delete store app, generate fresh migrations for catalog/customers/cart/orders"
```

---

## Self-Review Notes

- **Spec coverage:** All four app breakdowns, shared-utility relocation to
  `core`, string-style cross-app FKs, single `store/` URL prefix, fresh
  migrations, and `core` call-site updates from the spec are each covered by
  a task above.
- **Cross-cutting fix caught during planning:** admin `reverse()` URL names
  (`admin:store_product_changelist`, `admin:store_order_changelist`) and the
  `view_history` permission string (`store.view_history`) are namespaced by
  app label and were not called out explicitly in the spec — this plan
  updates them (`catalog/admin.py`, `customers/admin.py`,
  `customers/permissions.py`) since they'd otherwise silently 404 or
  mis-authorize after the rename.
- **Seed data:** the spec didn't mention `store/management/commands/`;
  this plan moves it into `catalog` (Task 1) since it only seeds
  collection/product data, and rewrites the hardcoded `store_*` table names
  in `seed.sql` to `catalog_*` — otherwise the command would silently break
  post-rename.
