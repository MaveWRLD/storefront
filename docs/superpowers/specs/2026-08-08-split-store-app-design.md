# Split `store` app into `catalog`, `cart`, `customers`, `orders`

Date: 2026-08-08

## Context

The `store` app currently holds four distinct bounded contexts (product catalog,
shopping cart, customer profile/address, and order processing) in one Django
app: models, serializers, views, admin, filters, permissions, pagination,
validators, signals, and management commands all live under `store/`. This
makes the app large and mixes unrelated responsibilities, and other apps
(`core`) already import from it directly.

The project's migrations were recently squashed to a single fresh
`0001_initial.py` per app (see git status), confirming there is no production
data to preserve — this refactor can ship clean, fresh migrations per new app
rather than attempting a history-preserving app split.

## Goals

- Break `store` into apps that each own one bounded context.
- Keep the public API surface identical (`store/...` URL prefix unchanged) —
  no breaking change for API clients.
- Move genuinely shared, non-domain-specific utilities (`DefaultPagination`,
  `IsAdminOrReadOnly`, `FullDjangoModelPermissions`) into `core`, which already
  plays the shared/platform role in this codebase.
- Update `core`'s existing cross-app imports (`core/admin.py`,
  `core/serializers.py`, `core/signals/handlers.py`) to point at the new apps.

## Non-goals

- No change to `likes`, `tags`, or `playground` — they only reference domain
  models through generic foreign keys / content types, so they are unaffected.
- No further splitting within the new apps (e.g. splitting `Review` or
  `Promotion` out of `catalog`) — out of scope per the chosen 4-app split.
- No migration-history preservation dance (`SeparateDatabaseAndState`, fake
  migrations to match old table names) — fresh initial migrations per app,
  since there's no production data.
- No change to authentication/user model (`core.User`) itself.

## App breakdown

### `catalog`
Owns product discovery.

- Models: `Product`, `Collection`, `Promotion`, `Review`
- Serializers: `CollectionSerializer`, `ProductSerializer`,
  `SimpleProductSerializer`, `ReviewSerializer`
- Views: `ProductViewSet`, `CollectionViewSet`, `ReviewViewSet`
- `filters.py`: `ProductFilter`
- `validators.py`: `validate_file_size` (currently unused by any model field,
  carried over as-is — not in scope to resolve dead code here)
- `admin.py`: `InventoryFilter`, `ProductAdmin`, `CollectionAdmin`
- `urls.py`: `products` router (with nested `reviews` under
  `products/<pk>/reviews/`), `collections` router
- No cross-app model dependencies. `Collection.featured_product`,
  `Review.product`, `Product.collection`, `Product.promotions` all stay
  intra-app FKs.

### `cart`
Owns the shopping cart, pre-checkout.

- Models: `Cart`, `CartItem`
- Serializers: `CartItemSerializer`, `CartSerializer`,
  `AddCartItemSerializer`, `UpdateCartItemSerializer`
- Views: `CartViewSet`, `CartItemViewSet`
- `urls.py`: `carts` router with nested `items` under `carts/<pk>/items/`
- Cross-app dependency: `CartItem.product` → `models.ForeignKey('catalog.Product', ...)`
  (string reference, per approved FK style). `AddCartItemSerializer` and
  `CartItemSerializer` import `catalog.serializers.SimpleProductSerializer`
  and validate against `catalog.models.Product`.

### `customers`
Owns the customer profile and address book, and the link from Django's
`User` to a `Customer`.

- Models: `Customer`, `Address`
- Serializers: `CustomerSerializer`
- Views: `CustomerViewSet` (including `history` and `me` actions)
- `permissions.py`: `ViewCustomerHistoryPermission` (customer-specific;
  stays here rather than moving to `core`)
- `admin.py`: `CustomerAdmin`
- `signals/handlers.py`: `create_customer_for_new_user` (post_save receiver
  on `settings.AUTH_USER_MODEL`) — moves here from `store/signals/handlers.py`
  since it exists to keep `Customer` in sync with `User`. `customers/apps.py`
  `ready()` imports it, mirroring the existing `core`/`store` pattern.
- `urls.py`: `customers` router
- No cross-app model dependencies (`Address.customer` is intra-app).

### `orders`
Owns order placement and checkout — the most coupled app by nature of the
domain (checkout reads from cart and catalog, writes against customer).

- Models: `Order`, `OrderItem`
- Serializers: `OrderSerializer`, `OrderItemSerializer`,
  `UpdateOrderSerializer`, `CreateOrderSerializer`
- Views: `OrderViewSet`
- `admin.py`: `OrderItemInline`, `OrderAdmin`
- `signals/__init__.py`: `order_created = Signal()` — moves here from
  `store/signals/__init__.py` since it's fired at order-creation time
- `urls.py`: `orders` router
- Cross-app dependencies (string FK refs):
  - `Order.customer` → `models.ForeignKey('customers.Customer', ...)`
  - `OrderItem.product` → `models.ForeignKey('catalog.Product', ...)`
  - `OrderItem.order` stays intra-app (`Order`)
- Cross-app imports: `OrderItemSerializer` imports
  `catalog.serializers.SimpleProductSerializer`; `CreateOrderSerializer`
  imports `cart.models.Cart`/`CartItem` (to consume the cart at checkout) and
  `customers.models.Customer` (to attach the order to the requesting user's
  customer record).

## Shared utilities → `core`

- `core/pagination.py`: `DefaultPagination` (used by `catalog.ProductViewSet`)
- `core/permissions.py`: `IsAdminOrReadOnly`, `FullDjangoModelPermissions`
  (used by `catalog` and `customers` views/admin)

`core` already holds the custom `User` model and cross-cutting signal
handling, so it's the natural home for permissions/pagination classes with no
single-domain owner.

## Dependency graph

```
catalog     customers
   ^            ^
   |            |
  cart          |
   ^            |
   |            |
   +--- orders -+

core -> catalog (ProductAdmin tag inline), customers (Customer in UserSerializer)
```

`INSTALLED_APPS` order doesn't affect Django's migration dependency
resolution (that's driven by the FK/migration graph, not list order), but for
readability list them as: `catalog`, `customers`, `cart`, `orders`, `core`.

## Cross-app FK style

Per approved decision: all cross-app foreign keys use Django's lazy string
form (`'app_label.Model'`) rather than importing the model class, e.g.:

```python
product = models.ForeignKey('catalog.Product', on_delete=models.CASCADE)
```

Intra-app FKs keep the existing direct-class style (e.g. `Product` model
class referenced within `catalog/models.py` itself).

## `core` call sites to update

- `core/admin.py`: `from store.models import Product` → `from catalog.models import Product`;
  `from store.admin import ProductAdmin` → `from catalog.admin import ProductAdmin`
- `core/serializers.py`: `from store.models import Customer` → `from customers.models import Customer`
- `core/signals/handlers.py`: `from store.signals import order_created` → `from orders.signals import order_created`

## URL routing

Single `store/` URL prefix is preserved for zero API breakage. `storefront/urls.py`
mounts all four apps' routers under that one prefix, e.g.:

```python
urlpatterns = [
    ...
    path('store/', include('catalog.urls')),
    path('store/', include('cart.urls')),
    path('store/', include('customers.urls')),
    path('store/', include('orders.urls')),
]
```

Each app keeps its own `urls.py` building its own `DefaultRouter` /
`NestedDefaultRouter` — nested routers (`products/<pk>/reviews/` in
`catalog`, `carts/<pk>/items/` in `cart`) stay defined within the owning
app since the parent and nested resource live together.

## Migrations

- Delete `store/` entirely, including `store/migrations/`.
- Generate fresh `0001_initial.py` for each of `catalog`, `cart`,
  `customers`, `orders` via `makemigrations` once the models are moved.
- No `SeparateDatabaseAndState` / fake-migration dance — this is a dev
  database with no data to preserve (consistent with the already-reset
  migration history visible in git status).
- Local dev environments should drop and recreate their database (or rerun
  `migrate` from zero) after this change lands.

## Testing

- `store/tests/test_collections.py` moves to `catalog/tests/test_collections.py`
  as-is (it tests `Collection`, which now lives in `catalog`).
- Placeholder `tests.py` files (empty, framework-generated) are created fresh
  for each new app by `startapp`; the existing empty `store/tests.py` is
  deleted along with the rest of `store/`.
- No new test coverage is being added as part of this refactor — it's a pure
  structural move. Existing tests must still pass after the move.

## Rollout / verification checklist

1. Create `catalog`, `cart`, `customers`, `orders` apps via `startapp`.
2. Move models/serializers/views/admin/filters/permissions/validators/signals
   per the breakdown above; update all imports to the new locations and to
   string FK refs where cross-app.
3. Move shared pagination/permissions classes into `core`.
4. Update `core/admin.py`, `core/serializers.py`, `core/signals/handlers.py`.
5. Update `storefront/settings.py` `INSTALLED_APPS` and `storefront/urls.py`.
6. Delete `store/` app directory entirely.
7. Generate fresh migrations for the 4 new apps; run `migrate` on a reset
   dev DB.
8. Run the full test suite (`python manage.py test`) — must pass.
9. Manually hit a few key endpoints (`store/products/`, `store/carts/`,
   `store/customers/me/`, `store/orders/`) to confirm the URL prefix and
   routing still resolve correctly.
