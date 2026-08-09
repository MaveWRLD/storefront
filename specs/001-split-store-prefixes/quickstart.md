# Quickstart: Validate the Store API Audience Split

## Prerequisites

- Local dev server running (`python manage.py runserver`), DB migrated, at least one staff user and one regular customer user with a token/session.
- A seeded product with a variant, so an order/return can be exercised end-to-end.

## Setup

```bash
python manage.py migrate
python manage.py createsuperuser   # if no staff user exists yet
python manage.py runserver
```

Obtain tokens via existing `auth/` (djoser JWT) endpoints for both a staff user and a customer user.

## Validate: old prefix is gone (spec FR-009)

```bash
curl -i http://localhost:8000/store/products/
```

Expected: no longer resolves as a customer-facing endpoint (404/route not found) — confirms the old single prefix was removed at cutover, not aliased.

## Validate: customer-facing flow (User Story 1)

```bash
# Browse (no auth)
curl http://localhost:8000/store-front/products/
curl http://localhost:8000/store-front/collections/

# Own profile (customer token)
curl -H "Authorization: Bearer $CUSTOMER_TOKEN" http://localhost:8000/store-front/customers/me/

# Cart -> order -> checkout
curl -X POST http://localhost:8000/store-front/carts/
curl -X POST http://localhost:8000/store-front/carts/{cart_id}/items/ -d '{"product_id": 1, "quantity": 1}'
curl -X POST http://localhost:8000/store-front/orders/ -d '{"cart_id": "{cart_id}"}'
curl -X POST http://localhost:8000/store-front/payments/initialize/ -d '{"order_id": 1}'

# Staff-only action rejected on the front prefix
curl -i -X DELETE -H "Authorization: Bearer $CUSTOMER_TOKEN" http://localhost:8000/store-front/products/1/
```

Expected: browsing and checkout calls succeed with the same data/shape as before the split (see [contracts/store-front.md](./contracts/store-front.md)); the DELETE is rejected (403/404, not exposed on this prefix at all).

## Validate: staff flow (User Story 2)

```bash
# Product/collection/image writes (staff token)
curl -X POST -H "Authorization: Bearer $STAFF_TOKEN" http://localhost:8000/store-admin/products/ -d '{...}'

# Manage any order
curl -H "Authorization: Bearer $STAFF_TOKEN" http://localhost:8000/store-admin/orders/
curl -X PATCH -H "Authorization: Bearer $STAFF_TOKEN" http://localhost:8000/store-admin/orders/1/ -d '{"status": "shipped"}'

# Reports
curl -H "Authorization: Bearer $STAFF_TOKEN" http://localhost:8000/store-admin/reports/sales/

# Non-staff rejected
curl -i -H "Authorization: Bearer $CUSTOMER_TOKEN" http://localhost:8000/store-admin/products/
```

Expected: staff calls succeed per [contracts/store-admin.md](./contracts/store-admin.md); the last call is rejected with a 403.

## Validate: schema/docs (User Story 3)

```bash
curl http://localhost:8000/api/schema/ | grep -o '"/store[^"]*"' | sort -u
```

Expected: every path starts with `/store-front/` or `/store-admin/`; zero paths start with `/store/`.

## Success criteria checked here

- SC-001, SC-005: schema grep above shows full endpoint coverage under the two new prefixes and zero under the old one.
- SC-002: the staff-only calls under `store-front/`/without a staff token are rejected.
- SC-003: the customer flow (browse → cart → order → payment) completes exactly as before.
