# Implementation Plan: Split Store API by Audience (store-front / store-admin)

**Branch**: `001-split-store-prefixes` | **Date**: 2026-08-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-split-store-prefixes/spec.md`

## Summary

Replace the single `store/` URL prefix with two audience-scoped prefixes, `store-front/` (customer-facing) and `store-admin/` (staff-only), with no backward-compat alias for the old prefix. For every existing view whose permission logic today branches on `request.user.is_staff` / method (Product, Collection, ProductImage, Customer, Order, Return), split it into two separate ViewSet classes — one customer-scoped, one admin-scoped — each with its own fixed permission class and its own router registration under the matching prefix, instead of one ViewSet with conditional `get_permissions()`/`get_queryset()` branching. Endpoints with no admin-side behavior (reviews, cart, payment) move under `store-front/` unchanged; endpoints with no customer-side behavior (reports) move under `store-admin/` unchanged.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: Django, Django REST Framework, `rest_framework_nested` (nested routers), `rest_framework_simplejwt`, `djoser`, `drf-spectacular`, `django-filter`

**Storage**: Existing relational DB via Django ORM (no schema changes — this feature is routing/permission reorganization only)

**Testing**: Existing project test suite (pytest / DRF `APITestCase`, whichever this repo already uses) — add tests per split endpoint

**Target Platform**: Linux server (Django web service)

**Project Type**: Web service (Django REST Framework backend), single project — no frontend/mobile in this repo

**Performance Goals**: No change from current behavior; routing/permission reorg only, not a performance feature

**Constraints**: No backward-compat alias for old `store/` prefix (clean cutover per spec FR-009); no change to existing permission outcomes (spec FR-003); no endpoint dropped or duplicated (spec FR-005)

**Scale/Scope**: 7 existing apps under `store/` (catalog, cart, customers, orders, payment, returns, reports); 5 resources need a customer/admin ViewSet split (Product, Collection, ProductImage, Customer, Order, Return); 3 resources move as-is (Review, Cart/CartItem → front; Reports → admin); 2 standalone `APIView`s (payment) move as-is → front

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled placeholder template (no ratified principles for this project). No gates to evaluate — treated as N/A. No complexity to justify.

## Project Structure

### Documentation (this feature)

```text
specs/001-split-store-prefixes/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
storefront/urls.py             # top-level router: replace store/ with store-front/ and store-admin/ includes

catalog/
├── views.py                   # ProductViewSet, CollectionViewSet, ProductImageViewSet (front, read-only)
│                               # + ProductAdminViewSet, CollectionAdminViewSet, ProductImageAdminViewSet (admin, full CRUD)
│                               # ReviewViewSet unchanged (front only)
├── urls_front.py               # products, collections, product images (read-only) + nested reviews (existing rules)
└── urls_admin.py               # products, collections, product images (write/full CRUD)

customers/
├── views.py                    # CustomerViewSet(front): `me` GET/PUT only
│                               # + CustomerAdminViewSet(admin): list/retrieve/update/delete + history
├── urls_front.py
└── urls_admin.py

orders/
├── views.py                    # OrderViewSet(front): create, own list/retrieve, lookup
│                               # + OrderAdminViewSet(admin): list all, patch, delete
├── urls_front.py
└── urls_admin.py

returns/
├── views.py                    # ReturnViewSet(front): create, retrieve (ownership-checked)
│                               # + ReturnAdminViewSet(admin): list, patch (review)
├── urls_front.py
└── urls_admin.py

cart/urls.py                    # unchanged content, included only under store-front/
payment/urls.py                 # unchanged content, included only under store-front/
reports/urls.py                 # unchanged content, included only under store-admin/
```

**Structure Decision**: Keep the existing per-app layout (catalog, customers, orders, payment, returns, reports, cart). For the 4 apps whose views today mix customer and staff logic in one class (catalog, customers, orders, returns), split each mixed ViewSet into two concrete ViewSet classes in the same `views.py` — a customer-scoped class with a fixed permission class (no `get_permissions()` branching) and an admin-scoped class (`IsAdminUser`) — and add per-audience `urls_front.py`/`urls_admin.py` router modules in place of the current single `urls.py`. Apps with no admin-side behavior (cart, payment) or no customer-side behavior (reports) keep a single `urls.py`, included only under the matching top-level prefix. `storefront/urls.py` replaces the `store/` includes with `store-front/` and `store-admin/` includes pointing at the new per-app URL modules.

## Complexity Tracking

*No constitution violations — this section is not needed.*
