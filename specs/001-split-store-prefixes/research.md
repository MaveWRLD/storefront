# Research: Split Store API by Audience

No `[NEEDS CLARIFICATION]` markers remain in the Technical Context — all decisions below come from inspecting the existing codebase (`storefront/urls.py` and each app's `views.py`/`urls.py`) rather than open unknowns. Recorded here per the standard research format for traceability.

## Decision: Split mixed ViewSets into a customer class and an admin class, instead of `get_permissions()` branching

**Rationale**: Per user direction for this feature ("have two separate viewset classes for customer and admin"). Today, four ViewSets encode both audiences in one class via conditional permissions/queryset logic:

- `catalog.views.ProductViewSet`, `CollectionViewSet`, `ProductImageViewSet` — all use `permission_classes = [IsAdminOrReadOnly]` (read open, write admin-only).
- `customers.views.CustomerViewSet` — `permission_classes = [IsAdminUser]` on the class, but the `me` action overrides to `IsAuthenticated`.
- `orders.views.OrderViewSet` — `get_permissions()` branches: `create`/`lookup` → `AllowAny`, `PATCH`/`DELETE` → `IsAdminUser`, else `IsAuthenticated`; `get_queryset()` branches on `user.is_staff` to return all orders vs. only the caller's.
- `returns.views.ReturnViewSet` — `get_permissions()` branches: `list`/`PATCH` → `IsAdminUser`, else `AllowAny`; ownership for `create`/`retrieve` is checked in the method body.

Splitting each into a customer-scoped class (fixed permission, queryset limited to the caller's own data) and an admin-scoped class (fixed `IsAdminUser`, queryset over all rows) removes the conditional branching, makes the permission for each URL obvious from its class alone, and maps directly onto the two new prefixes (spec FR-002, FR-003, FR-008).

**Alternatives considered**:
- Keep one ViewSet per resource, register it twice (once under each prefix) relying on existing `get_permissions()`: rejected — doesn't satisfy the user's explicit direction, and still requires a caller to read method bodies to know what a given URL allows.
- Introduce a shared permission/mixin class instead of two ViewSets: rejected for this feature — doesn't achieve "two separate viewset classes" and doesn't simplify the per-audience router registration the spec's URL split needs.

## Decision: Resources with only one audience move as-is (no split)

**Rationale**: `catalog.views.ReviewViewSet` (`IsAuthenticatedOrReadOnly`, no admin-only action today), `cart` (`CartViewSet`/`CartItemViewSet`, no admin action), and `payment` (`InitializePaymentView`/`VerifyPaymentView`, `AllowAny`) have no staff-only behavior to separate out — they move under `store-front/` unchanged. `reports.views.SalesReportView` (`IsAdminUser`) has no customer-facing behavior — it moves under `store-admin/` unchanged. This satisfies spec FR-007 (classify by current permission gate) without inventing a split that doesn't exist today.

**Alternatives considered**: Splitting these anyway for symmetry — rejected as unnecessary churn; spec requires correct classification, not uniform structure.

## Decision: Old `store/` prefix removed at cutover, no alias/redirect

**Rationale**: Resolved directly by the spec's clarification answer (FR-009) — no external consumers to protect.

**Alternatives considered**: Temporary redirect/alias — explicitly rejected by the spec owner.
