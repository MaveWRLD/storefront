# Contract: `store-front/` (customer-facing)

All paths below are relative to `store-front/`. Behavior/response shape is unchanged from today's equivalent `store/` endpoint — only the prefix and, for split resources, the serving class change.

| Method | Path | ViewSet / View | Permission |
|---|---|---|---|
| GET | `products/` | `catalog.ProductViewSet` | open (read) |
| GET | `products/{id}/` | `catalog.ProductViewSet` | open (read) |
| GET | `products/{product_pk}/images/` | `catalog.ProductImageViewSet` | open (read) |
| GET | `products/{product_pk}/images/{id}/` | `catalog.ProductImageViewSet` | open (read) |
| GET | `products/{product_pk}/reviews/` | `catalog.ReviewViewSet` | open (read) |
| GET | `products/{product_pk}/reviews/{id}/` | `catalog.ReviewViewSet` | open (read) |
| POST | `products/{product_pk}/reviews/` | `catalog.ReviewViewSet` | authenticated |
| PUT/PATCH | `products/{product_pk}/reviews/{id}/` | `catalog.ReviewViewSet` | authenticated (own review) |
| DELETE | `products/{product_pk}/reviews/{id}/` | `catalog.ReviewViewSet` | authenticated (own review) |
| GET | `collections/` | `catalog.CollectionViewSet` | open (read) |
| GET | `collections/{id}/` | `catalog.CollectionViewSet` | open (read) |
| GET/POST | `carts/` | `cart.CartViewSet` | open (unchanged) |
| GET | `carts/{id}/` | `cart.CartViewSet` | open (unchanged) |
| DELETE | `carts/{id}/` | `cart.CartViewSet` | open (unchanged) |
| GET/POST | `carts/{cart_pk}/items/` | `cart.CartItemViewSet` | open (unchanged) |
| PATCH/DELETE | `carts/{cart_pk}/items/{id}/` | `cart.CartItemViewSet` | open (unchanged) |
| GET | `customers/me/` | `customers.CustomerViewSet` | authenticated (own profile) |
| PUT | `customers/me/` | `customers.CustomerViewSet` | authenticated (own profile) |
| POST | `orders/` | `orders.OrderViewSet` | open (guest checkout allowed) |
| POST | `orders/lookup/` | `orders.OrderViewSet` | open (guest order lookup) |
| GET | `orders/` | `orders.OrderViewSet` | authenticated (own orders only) |
| GET | `orders/{id}/` | `orders.OrderViewSet` | authenticated (own order only) |
| POST | `returns/` | `returns.ReturnViewSet` | open (guest allowed) |
| GET | `returns/{id}/` | `returns.ReturnViewSet` | open, ownership-checked in view |
| POST | `payments/initialize/` | `payment.InitializePaymentView` | open (unchanged) |
| POST | `payments/verify/` | `payment.VerifyPaymentView` | open (unchanged) |

Not included: any create/update/delete on products, collections, or product images; any list of all customers/orders/returns; any admin `history`/review action; reports. Those live under [store-admin.md](./store-admin.md).
