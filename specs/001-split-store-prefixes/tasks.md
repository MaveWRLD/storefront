# Tasks: Split Store API by Audience (store-front / store-admin)

**Input**: Design documents from `/specs/001-split-store-prefixes/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: This feature has no new business logic, so no new tests are added. The existing regression suite already covers every endpoint being moved; tasks below update its hardcoded `/store/...` paths to the correct new prefix and require the suite to stay green — this doubles as the test-coverage check for the split.

**Organization**: Tasks are grouped by user story (spec.md) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

Django project at repo root. Per-app layout: `<app>/views.py`, `<app>/urls.py` (single-audience apps) or `<app>/urls_front.py` + `<app>/urls_admin.py` (split apps), `<app>/tests/`. Top-level routing in `storefront/urls.py`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold the per-app URL modules the split apps need before routing can be wired.

- [X] T001 [P] Create `catalog/urls_front.py` and `catalog/urls_admin.py` (each with an empty `rest_framework_nested.routers.DefaultRouter` and `urlpatterns = router.urls`), replacing `catalog/urls.py`
- [X] T002 [P] Create `customers/urls_front.py` and `customers/urls_admin.py` (each with an empty `DefaultRouter`/`urlpatterns = []`), replacing `customers/urls.py`
- [X] T003 [P] Create `orders/urls_front.py` and `orders/urls_admin.py` (each with an empty `DefaultRouter`/`urlpatterns = []`), replacing `orders/urls.py`
- [X] T004 [P] Create `returns/urls_front.py` and `returns/urls_admin.py` (each with an empty `DefaultRouter`/`urlpatterns = []`), replacing `returns/urls.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Split every mixed-audience ViewSet into a customer class and an admin class (per plan.md/research.md), and wire the two new top-level prefixes. **MUST complete before any user story.**

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 In `catalog/views.py`, split `ProductViewSet` into a front `ProductViewSet` (`ReadOnlyModelViewSet`, list/retrieve only, open read access matching today's `IsAdminOrReadOnly` read side) and a new `ProductAdminViewSet` (`ModelViewSet`, full CRUD including the existing `destroy()` order-item guard, `permission_classes = [IsAdminUser]`)
- [X] T006 In `catalog/views.py`, split `CollectionViewSet` into a front `CollectionViewSet` (`ReadOnlyModelViewSet`) and a new `CollectionAdminViewSet` (`ModelViewSet`, keeps the existing `destroy()` guard, `permission_classes = [IsAdminUser]`) (depends on T005 — same file)
- [X] T007 In `catalog/views.py`, split `ProductImageViewSet` into a front `ProductImageViewSet` (`ReadOnlyModelViewSet`) and a new `ProductImageAdminViewSet` (`ModelViewSet`, `permission_classes = [IsAdminUser]`) (depends on T006 — same file)
- [X] T008 [P] In `customers/views.py`, split `CustomerViewSet` into a front `CustomerViewSet` exposing only the existing `me` GET/PUT action (`permission_classes = [IsAuthenticated]`) and a new `CustomerAdminViewSet` (`ModelViewSet` + the existing `history` action, `permission_classes = [IsAdminUser]`)
- [X] T009 [P] In `orders/views.py`, split `OrderViewSet` into a front `OrderViewSet` (create, the `lookup` action, and list/retrieve limited via `get_queryset()` to the caller's own orders — no `is_staff` branch left) and a new `OrderAdminViewSet` (`ModelViewSet`: list/retrieve all orders, update, partial_update, destroy, `permission_classes = [IsAdminUser]`)
- [X] T010 [P] In `returns/views.py`, split `ReturnViewSet` into a front `ReturnViewSet` (create, retrieve with the existing ownership check, `permission_classes = [AllowAny]`) and a new `ReturnAdminViewSet` (list, partial_update/review, `permission_classes = [IsAdminUser]`)
- [X] T011 Update `storefront/urls.py`: remove the `store/` include block; add a `store-front/` group (updated `store_api_root`, `catalog.urls_front`, `cart.urls`, `customers.urls_front`, `orders.urls_front`, `payment.urls`, `returns.urls_front`) and a `store-admin/` group (`catalog.urls_admin`, `customers.urls_admin`, `orders.urls_admin`, `returns.urls_admin`, `reports.urls`) (depends on T001-T004 for the imported modules to exist)

**Checkpoint**: Server boots; `store-front/` and `store-admin/` resolve (empty router lists for the four split apps until their story phase registers routes); `cart/`, `payment/`, `reports/`, and catalog reviews are already live since their `urls.py` is included unchanged.

---

## Phase 3: User Story 1 - Shopper browses and manages their own account (Priority: P1) 🎯 MVP

**Goal**: Every customer-facing action (browse products/collections, reviews, cart, own orders, own profile, checkout/payment) works under `store-front/`.

**Independent Test**: Call each customer-facing endpoint under `store-front/` (see [contracts/store-front.md](./contracts/store-front.md)) and confirm behavior/response matches what `store/` returned before the split; confirm a staff-only action attempted through this prefix is rejected.

### Implementation for User Story 1

- [X] T012 [US1] Register `products/` (root + nested `images/`, `reviews/`) and `collections/` routes in `catalog/urls_front.py` using the front `ProductViewSet`, `ProductImageViewSet`, `ReviewViewSet`, `CollectionViewSet` (mirror the existing router/nested-router structure from the old `catalog/urls.py`)
- [X] T013 [US1] Register the `customers/me/` route in `customers/urls_front.py` using the front `CustomerViewSet`
- [X] T014 [US1] Register `orders/` (create, `lookup/`, list/retrieve) routes in `orders/urls_front.py` using the front `OrderViewSet`
- [X] T015 [US1] Register `returns/` (create, retrieve) routes in `returns/urls_front.py` using the front `ReturnViewSet`
- [X] T016 [P] [US1] Update `catalog/tests/test_browse_products.py`: change hardcoded `/store/products/...` paths to `/store-front/products/...`
- [X] T017 [P] [US1] Update `catalog/tests/test_search_filter_products.py`: change `/store/products/...` paths to `/store-front/products/...`
- [X] T018 [P] [US1] Update `catalog/tests/test_product_detail.py`: change `/store/products/...` paths to `/store-front/products/...`
- [X] T019 [P] [US1] Update `catalog/tests/test_collections.py`: change `/store/collections/...` paths to `/store-front/collections/...`
- [X] T020 [P] [US1] Update `catalog/tests/test_leave_product_review.py`: change `/store/products/.../reviews/...` paths to `/store-front/products/.../reviews/...`
- [X] T021 [P] [US1] Update `cart/tests/test_abandon_checkout.py`: change `/store/carts/...` paths to `/store-front/carts/...`
- [X] T022 [P] [US1] Update `orders/tests/test_stock_revalidation.py`: change `/store/orders/` path to `/store-front/orders/`
- [X] T023 [P] [US1] Update `orders/tests/test_track_order.py`: change `/store/orders/lookup/`, `/store/payments/initialize/`, `/store/payments/verify/` paths to `/store-front/...`
- [X] T024 [P] [US1] Update `payment/tests/test_payment_session_expiry.py`: change `/store/payments/...` paths to `/store-front/payments/...`
- [X] T025 [P] [US1] Update `payment/tests/test_retry_failed_payment.py`: change `/store/payments/...` paths to `/store-front/payments/...`
- [X] T026 [P] [US1] Update `returns/tests/test_request_return.py`: change `/store/returns/...` paths to `/store-front/returns/...`
- [X] T027 [US1] Run `pytest catalog/tests cart/tests orders/tests/test_stock_revalidation.py orders/tests/test_track_order.py payment/tests returns/tests/test_request_return.py` and fix any regressions until green (depends on T012-T026)

**Checkpoint**: User Story 1 is fully functional and testable independently of User Story 2/3.

---

## Phase 4: User Story 2 - Staff manages catalog, orders, and reports (Priority: P2)

**Goal**: Every staff-only action (product/collection/image CRUD, manage any order, reports) works under `store-admin/` and rejects non-staff callers.

**Independent Test**: Call each staff-only endpoint under `store-admin/` (see [contracts/store-admin.md](./contracts/store-admin.md)) with a staff token and confirm it behaves as before the split; call the same endpoints without a staff token and confirm rejection.

### Implementation for User Story 2

- [X] T028 [US2] Register `products/` (root + nested `images/`) and `collections/` CRUD routes in `catalog/urls_admin.py` using `ProductAdminViewSet`, `ProductImageAdminViewSet`, `CollectionAdminViewSet`
- [X] T029 [US2] Register `customers/` (list/retrieve/update/delete + `history`) routes in `customers/urls_admin.py` using `CustomerAdminViewSet`
- [X] T030 [US2] Register `orders/` (list/retrieve all, update, destroy) routes in `orders/urls_admin.py` using `OrderAdminViewSet`
- [X] T031 [US2] Register `returns/` (list, review via partial_update) routes in `returns/urls_admin.py` using `ReturnAdminViewSet`
- [X] T032 [P] [US2] Update `catalog/tests/test_create_product.py`: change `/store/products/...` paths to `/store-admin/products/...`
- [X] T033 [P] [US2] Update `catalog/tests/test_update_product.py`: change `/store/products/...` paths to `/store-admin/products/...`
- [X] T034 [P] [US2] Update `customers/tests/test_manage_customers.py`: change `/store/customers/...` paths to `/store-admin/customers/...`
- [X] T035 [P] [US2] Update `orders/tests/test_handle_failed_delivery_pickup_no_show.py`: change `/store/orders/...` paths to `/store-admin/orders/...`
- [X] T036 [P] [US2] Update `orders/tests/test_pickup_ready_order.py`: change `/store/orders/...` paths to `/store-admin/orders/...`
- [X] T037 [P] [US2] Update `orders/tests/test_receive_delivered_order.py`: change `/store/orders/...` paths to `/store-admin/orders/...`
- [X] T038 [P] [US2] Update `orders/tests/test_update_fulfillment_status.py`: change `/store/orders/...` paths to `/store-admin/orders/...`
- [X] T039 [P] [US2] Update `returns/tests/test_review_return_requests.py`: change `/store/returns/...` paths to `/store-admin/returns/...`
- [X] T040 [P] [US2] Update `reports/tests/test_view_reports.py`: change `/store/reports/...` paths to `/store-admin/reports/...`
- [X] T041 [US2] Run `pytest catalog/tests/test_create_product.py catalog/tests/test_update_product.py customers/tests orders/tests/test_handle_failed_delivery_pickup_no_show.py orders/tests/test_pickup_ready_order.py orders/tests/test_receive_delivered_order.py orders/tests/test_update_fulfillment_status.py returns/tests/test_review_return_requests.py reports/tests` and fix any regressions until green (depends on T028-T040)

**Checkpoint**: User Stories 1 AND 2 both work independently.

---

## Phase 5: User Story 3 - Integrator/developer discovers the API surface (Priority: P3)

**Goal**: The published schema shows every endpoint under exactly one of the two new prefixes, with the prefix alone indicating the required audience.

**Independent Test**: Fetch the schema and confirm every `/store*` path starts with `/store-front/` or `/store-admin/`, with zero remaining under `/store/`.

### Implementation for User Story 3

- [X] T042 [US3] Fetch `GET /api/schema/` (or run `python manage.py spectacular --file schema.yml`) and confirm every path is prefixed `store-front/` or `store-admin/` and matches the classification in [data-model.md](./data-model.md); fix any mis-registered route found
- [X] T043 [US3] Run the schema-check command from [quickstart.md](./quickstart.md) (`curl .../api/schema/ | grep -o '"/store[^"]*"' | sort -u`) and confirm zero paths start with `/store/`

**Checkpoint**: All user stories are independently functional; the API surface is fully documented under the new prefixes.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Fix up the few existing tests that exercise both audiences in one file, sweep for anything missed, and do a full-suite pass.

- [X] T044 [P] Update `orders/tests/test_view_orders.py`: `admin_client` calls → `/store-admin/orders/`, plain `client` calls → `/store-front/orders/`
- [X] T045 [P] Update `cart/tests/test_manage_inventory_mark_unavailable.py`: cart and product-read calls → `/store-front/...`, the admin stock-update `patch` call → `/store-admin/products/...`
- [X] T046 [P] Update `returns/tests/test_track_return_outcome.py`: `admin_client.patch` (review/approve/reject) calls → `/store-admin/returns/...`, plain `client.get`/`client.patch` calls → `/store-front/returns/...`
- [X] T047 Run `grep -rn "'/store/\|\"/store/" --include="*.py" .` from repo root and update or remove any remaining hardcoded `/store/` reference not already covered above
- [X] T048 Run the full test suite (`pytest`) and confirm all tests pass
- [X] T049 Execute the remaining [quickstart.md](./quickstart.md) scenarios end-to-end (old-prefix removal, customer flow, staff flow) and confirm every expected outcome

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001-T004 create the modules T011 imports). BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion. No dependency on US2/US3.
- **User Story 2 (Phase 4)**: Depends on Foundational completion. Independent of US1 (different files: `urls_admin.py` vs `urls_front.py`, different test files).
- **User Story 3 (Phase 5)**: Depends on Foundational completion; in practice most meaningful once US1 and US2 have registered their routes, since it validates the full schema.
- **Polish (Phase 6)**: Depends on US1 and US2 being complete (the mixed-audience test files touch endpoints from both).

### Within Each Phase

- Foundational: T005→T006→T007 are sequential (same file, `catalog/views.py`); T008, T009, T010 are each in a different file and can run in parallel with each other and with the T005-T007 chain; T011 needs T001-T004 done first.
- User Story 1: T012-T015 (routing) before T016-T026 (test path updates) before T027 (verification run).
- User Story 2: T028-T031 (routing) before T032-T040 (test path updates) before T041 (verification run).

### Parallel Opportunities

- All Setup tasks (T001-T004) can run in parallel — four different files.
- T008, T009, T010 in Foundational can run in parallel with each other and with the catalog chain (T005-T007).
- All test-path-update tasks within a story (T016-T026, T032-T040, T044-T046) can run in parallel — each touches a different file.
- Once Foundational is done, User Story 1 and User Story 2 can be worked entirely in parallel (disjoint files: `urls_front.py`/front tests vs. `urls_admin.py`/admin tests).

---

## Parallel Example: User Story 1

```bash
# Launch all test-path updates for User Story 1 together (after T012-T015 routing is done):
Task: "Update catalog/tests/test_browse_products.py paths to /store-front/"
Task: "Update catalog/tests/test_search_filter_products.py paths to /store-front/"
Task: "Update catalog/tests/test_product_detail.py paths to /store-front/"
Task: "Update catalog/tests/test_collections.py paths to /store-front/"
Task: "Update catalog/tests/test_leave_product_review.py paths to /store-front/"
Task: "Update cart/tests/test_abandon_checkout.py paths to /store-front/"
Task: "Update orders/tests/test_stock_revalidation.py paths to /store-front/"
Task: "Update orders/tests/test_track_order.py paths to /store-front/"
Task: "Update payment/tests/test_payment_session_expiry.py paths to /store-front/"
Task: "Update payment/tests/test_retry_failed_payment.py paths to /store-front/"
Task: "Update returns/tests/test_request_return.py paths to /store-front/"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run the User Story 1 test files, confirm green
5. Deploy/demo if ready — customers can fully shop through `store-front/`

### Incremental Delivery

1. Setup + Foundational → foundation ready (viewsets split, top-level routing wired)
2. Add User Story 1 → validate independently → deploy/demo (MVP)
3. Add User Story 2 → validate independently → deploy/demo
4. Add User Story 3 → validate schema → deploy/demo
5. Polish → fix the 3 mixed-audience test files, full-suite pass, final quickstart run

---

## Notes

- No new persisted entities or migrations — this is a routing/permission reorganization (see [data-model.md](./data-model.md)).
- Reviews (catalog), Cart, and Payment have no admin-only behavior today — they move under `store-front/` unchanged (no split ViewSet needed).
- Reports have no customer-facing behavior today — it moves under `store-admin/` unchanged.
- Old `store/` prefix is removed at cutover, not aliased (spec FR-009, T011) — this is an intentional breaking change with no external consumers to protect.
- [P] tasks touch different files with no dependency on an incomplete task; verify before marking a task [P].
- Commit after each task or logical group.
