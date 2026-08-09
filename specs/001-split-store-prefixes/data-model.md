# Data Model: Split Store API by Audience

This feature reorganizes URL routing and permission classes only — it does not add, remove, or modify any persisted model or database schema. `Product`, `Collection`, `ProductImage`, `Review`, `Cart`/`CartItem`, `Customer`, `Order`, `Return` keep their existing fields and relationships unchanged.

The entities below are the conceptual entities from the spec, expressed as the routing/permission classification each existing model's ViewSet(s) must satisfy.

## Endpoint Classification

Every existing endpoint is classified into exactly one row per audience it serves (spec FR-005, FR-007, FR-008).

| Resource (model) | Customer-facing (`store-front/`) | Staff-only (`store-admin/`) |
|---|---|---|
| Product | list, retrieve (read-only) | list, retrieve, create, update, partial_update, destroy |
| Collection | list, retrieve (read-only) | list, retrieve, create, update, partial_update, destroy |
| ProductImage (nested under product) | list, retrieve (read-only) | list, retrieve, create, update, partial_update, destroy |
| Review (nested under product) | list, retrieve, create, update, partial_update, destroy (own review; unchanged) | — (no admin-only action exists today) |
| Cart / CartItem | full CRUD (unchanged) | — (no admin-only action exists today) |
| Customer | `me` retrieve/update (own profile only) | list, retrieve, update, partial_update, destroy, `history` action (any customer) |
| Order | create, `lookup` (guest), list/retrieve (own orders only) | list/retrieve (all orders), update, partial_update, destroy |
| Return | create, retrieve (ownership-checked; guest allowed) | list, partial_update (review/approve/reject) |
| Payment (initialize/verify) | both actions (unchanged) | — (no admin-only action exists today) |
| Sales report | — (no customer-facing action exists today) | sales report (unchanged) |

## ViewSet → Class Mapping

Reflects the "two separate viewset classes for customer and admin" decision (see [research.md](./research.md)). Only resources with both an admin and a customer behavior today get a second class; the rest keep their single existing class, remapped to one prefix.

| App | Front class (`store-front/`) | Admin class (`store-admin/`) |
|---|---|---|
| catalog | `ProductViewSet` (read-only) | `ProductAdminViewSet` (full CRUD) |
| catalog | `CollectionViewSet` (read-only) | `CollectionAdminViewSet` (full CRUD) |
| catalog | `ProductImageViewSet` (read-only) | `ProductImageAdminViewSet` (full CRUD) |
| catalog | `ReviewViewSet` (unchanged) | *(none)* |
| cart | `CartViewSet`, `CartItemViewSet` (unchanged) | *(none)* |
| customers | `CustomerViewSet` (own profile only, `me` action) | `CustomerAdminViewSet` (full CRUD + `history`) |
| orders | `OrderViewSet` (create, own list/retrieve, `lookup`) | `OrderAdminViewSet` (list/retrieve all, update, destroy) |
| returns | `ReturnViewSet` (create, ownership-checked retrieve) | `ReturnAdminViewSet` (list, review via partial_update) |
| payment | `InitializePaymentView`, `VerifyPaymentView` (unchanged) | *(none)* |
| reports | *(none)* | `SalesReportView` (unchanged) |

## Permission Rules (unchanged outcomes, per spec FR-003)

- Front classes: fixed permission per class (`AllowAny`, `IsAuthenticatedOrReadOnly`, or `IsAuthenticated`, matching today's non-admin branch), queryset scoped to the requesting user's own data where applicable (own orders, own returns, own profile).
- Admin classes: fixed `IsAdminUser`, queryset over all rows — no per-request branching needed since the class itself is admin-only.
