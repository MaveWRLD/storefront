# Contract: `store-admin/` (staff-only)

All paths below are relative to `store-admin/`. Every endpoint requires `IsAdminUser` (staff). Behavior/response shape is unchanged from today's equivalent `store/` endpoint — only the prefix and, for split resources, the serving class change.

| Method | Path | ViewSet / View | Permission |
|---|---|---|---|
| GET/POST | `products/` | `catalog.ProductAdminViewSet` | admin |
| GET/PUT/PATCH/DELETE | `products/{id}/` | `catalog.ProductAdminViewSet` | admin |
| GET/POST | `products/{product_pk}/images/` | `catalog.ProductImageAdminViewSet` | admin |
| GET/PUT/PATCH/DELETE | `products/{product_pk}/images/{id}/` | `catalog.ProductImageAdminViewSet` | admin |
| GET/POST | `collections/` | `catalog.CollectionAdminViewSet` | admin |
| GET/PUT/PATCH/DELETE | `collections/{id}/` | `catalog.CollectionAdminViewSet` | admin |
| GET | `customers/` | `customers.CustomerAdminViewSet` | admin |
| GET/PUT/PATCH/DELETE | `customers/{id}/` | `customers.CustomerAdminViewSet` | admin |
| GET | `customers/{id}/history/` | `customers.CustomerAdminViewSet` | admin |
| GET | `orders/` | `orders.OrderAdminViewSet` | admin (all orders) |
| GET | `orders/{id}/` | `orders.OrderAdminViewSet` | admin (any order) |
| PATCH | `orders/{id}/` | `orders.OrderAdminViewSet` | admin |
| DELETE | `orders/{id}/` | `orders.OrderAdminViewSet` | admin |
| GET | `returns/` | `returns.ReturnAdminViewSet` | admin |
| PATCH | `returns/{id}/` | `returns.ReturnAdminViewSet` | admin (approve/reject) |
| GET | `reports/sales/` | `reports.SalesReportView` | admin (unchanged) |

Not included: any read-only browsing, own-profile, own-order, own-return, review, cart, or payment endpoint. Those live under [store-front.md](./store-front.md).
