# Data Model: Model Indexing for Faster Reads

No new entities — this feature adds indexes to existing models only. No field/relationship/behavior changes. Each row below is one index to add via `Meta.indexes` (or `unique=True`/`db_index=True` where noted), grounded in the baseline audit in `research.md` (R9).

## catalog app

| Model | Index | Type | Supports (query pattern) |
|---|---|---|---|
| `Product` | `slug` | single, `unique=True` (also fixes a correctness gap, not just perf) | Slug-based detail lookup |
| `Product` | `status` | single | Filter published/draft/archived listings |
| `Product` | `collection`, `status` | composite | Category page: products in collection X with status Y |
| `Product` | `-last_update` | single | Sort by recently updated |
| `Variant` | `track_inventory`, `inventory` | composite, partial (`condition=Q(track_inventory=True)`) | "in stock" filtering |
| `Review` | `product`, `-date` | composite | Reviews for a product, newest first |

## orders app

| Model | Index | Type | Supports (query pattern) |
|---|---|---|---|
| `Order` | `customer`, `-placed_at` | composite | Order history for a customer, newest first |
| `Order` | `status` | single | Admin/fulfillment dashboard filter |
| `Order` | `payment_status` | single | Payment-status dashboard filter |
| `Order` | `fulfillment_method` | single | Fulfillment-method filter |
| `Order` | `guest_email` | single | Guest order lookup by email |

## customers app

| Model | Index | Type | Supports (query pattern) |
|---|---|---|---|
| `Customer` | `membership` | single | Filter by membership tier |

(`Customer.user` already unique via `OneToOneField` — no change needed.)

## cart app

| Model | Index | Type | Supports (query pattern) |
|---|---|---|---|
| `Cart` | `last_activity` | single | Abandoned-cart TTL sweep |

## likes app

| Model | Index | Type | Supports (query pattern) |
|---|---|---|---|
| `LikedItem` | `content_type`, `object_id` | composite | Generic-relation lookup ("who liked this object") |
| `LikedItem` | `user`, `content_type`, `object_id` | composite, `unique=True` | Prevent duplicate likes + fast "has user X liked object Y" check |

## tags app

| Model | Index | Type | Supports (query pattern) |
|---|---|---|---|
| `TaggedItem` | `content_type`, `object_id` | composite | `TaggedItemManager.get_tags_for` filter |

## notifications app

| Model | Index | Type | Supports (query pattern) |
|---|---|---|---|
| `Notification` | `order`, `-sent_at` | composite | Notifications for an order, newest first (matches existing `Meta.ordering`) |
| `Notification` | `event_type` | single | Filter by event type |

## returns app

| Model | Index | Type | Supports (query pattern) |
|---|---|---|---|
| `Return` | `status` | single | Admin review queue filter |
| `Return` | `-requested_at` | single | Sort by request date |

## payment app

| Model | Index | Type | Supports (query pattern) |
|---|---|---|---|
| `Payment` | `order`, `-created_at` | composite | Payments for an order, newest first (matches existing `Meta.ordering`) |
| `Payment` | `status` | single | Filter by payment status |

(`Payment.reference` already unique/indexed — no change needed.)

## core app

| Model | Index | Type | Supports (query pattern) |
|---|---|---|---|
| `User` | `is_active`, `is_staff` | composite | Admin user-management filters |

(`User.email` already unique/indexed — no change needed.)

## Pre-migration integrity checks required (FR-004)

Run before applying the `unique=True` additions below, per research.md R6:

- `catalog.Product.slug` → unique — audit for duplicate slugs first.
- `likes.LikedItem` (`user`, `content_type`, `object_id`) → unique — audit for existing duplicate likes first.

## Indexes Added (implementation record)

All indexes below were applied via `Meta.indexes` (or `unique=True`/`UniqueConstraint` where noted) and shipped in one migration per app. Each matches the corresponding row in the tables above exactly — see migration files for generated SQL.

| App | Migration | Indexes |
|---|---|---|
| catalog | `0007_alter_product_slug_and_more` | `Product.slug` unique, `Product(status)`, `Product(collection, status)`, `Product(-last_update)`, `Review(product, -date)`, `Variant(track_inventory, inventory)` partial (`WHERE track_inventory`) |
| orders | `0010_order_orders_orde_custome_7b68ab_idx_and_more` | `Order(customer, -placed_at)`, `Order(status)`, `Order(payment_status)`, `Order(fulfillment_method)`, `Order(guest_email)` |
| customers | `0002_customer_customers_c_members_fac1cd_idx` | `Customer(membership)` |
| cart | `0004_cart_cart_cart_last_ac_251660_idx` | `Cart(last_activity)` |
| likes | `0002_likeditem_likes_liked_content_7292dd_idx_and_more` | `LikedItem(content_type, object_id)`, unique constraint `(user, content_type, object_id)` |
| notifications | `0002_notification_notificatio_order_i_c74624_idx_and_more` | `Notification(order, -sent_at)`, `Notification(event_type)` |
| tags | `0002_taggeditem_tags_tagged_content_eaa81e_idx` | `TaggedItem(content_type, object_id)` |
| returns | `0003_return_returns_ret_status_e1e871_idx_and_more` | `Return(status)`, `Return(-requested_at)` |
| payment | `0002_payment_payment_pay_order_i_c315bf_idx_and_more` | `Payment(order, -created_at)`, `Payment(status)` |
| core | `0002_user_core_user_is_acti_ec7de3_idx` | `User(is_active, is_staff)` |

Verified: all migrations apply and reverse cleanly (`migrate <app> <prev>` then forward); full existing pytest suite (134 tests) passes unchanged post-migration.

**Deferred**: SC-001 (<200ms latency) and SC-003 (≤10% write regression) require a 10k+-row seeded dataset per `quickstart.md`. The repo's `catalog/management/commands/seed_db.py` is currently stale (references a removed `Product.unit_price` field) and fails against the current schema, so that volume-scale measurement wasn't runnable in this environment. Structural verification (migration SQL matches `data-model.md`, `EXPLAIN`-visible index presence, reversibility, full regression suite) is complete; fixing `seed_db.py` is a separate pre-existing issue, not part of this feature's scope.

## Non-goals (explicitly not indexed here)

- `Variant.unit_price` — no current sort/filter-by-price read path identified in existing code; revisit if a price-filter feature ships.
- Free-text fields (`Tag.label`, `Notification.recipient`) — plain B-tree offers little benefit for partial/text search; out of scope per spec Assumptions (no new search infra).
