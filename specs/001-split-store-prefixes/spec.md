# Feature Specification: Split Store API by Audience (store-front / store-admin)

**Feature Branch**: `[001-split-store-prefixes]`

**Created**: 2026-08-09

**Status**: Draft

**Input**: User description: "Idea: instead of one store/ prefix holding everything, split into two prefixes by audience: store-front/ — customer-facing actions: browse products, collections, reviews, cart, own orders, own customer profile, checkout/payment. Mostly read + a few writes and deletes. store-admin/ — staff-only actions: create/update/delete products, collections, product images, manage all orders, reports. Anything gated by admin permission today."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Shopper browses and manages their own account (Priority: P1)

A customer uses the API to browse products and collections, read and write reviews, manage their cart, view/manage their own orders, manage their own customer profile, and complete checkout/payment — all through a clearly customer-scoped part of the API.

**Why this priority**: This is the highest-traffic, revenue-generating path. It must keep working without disruption during and after the split.

**Independent Test**: Can be fully tested by calling the customer-facing endpoints (products, collections, reviews, cart, own orders, own profile, checkout/payment) under the new customer-facing prefix and confirming responses and permissions match current behavior.

**Acceptance Scenarios**:

1. **Given** an authenticated customer, **When** they browse products, collections, and reviews, **Then** they get the same data as before, served from the customer-facing prefix.
2. **Given** an authenticated customer, **When** they add items to their cart, place an order, or complete checkout/payment, **Then** the action succeeds exactly as it does today, served from the customer-facing prefix.
3. **Given** an authenticated customer, **When** they view or update their own customer profile, **Then** they see/modify only their own data.
4. **Given** an authenticated customer, **When** they attempt a staff-only action (e.g., deleting a product, viewing another customer's orders), **Then** the request is rejected, regardless of which prefix they call.

---

### User Story 2 - Staff manages catalog, orders, and reports (Priority: P2)

A staff member with admin permission uses the API to create/update/delete products, collections, and product images, manage all customer orders, and view reports — all through a clearly staff-scoped part of the API.

**Why this priority**: Staff operations are lower-traffic than shopper traffic but are the reason the split exists — isolating them makes permissions, docs, and monitoring clearer and reduces the risk of an admin-only action being reachable without the right permission check.

**Independent Test**: Can be fully tested by calling each staff-only endpoint under the new staff prefix and confirming it requires admin permission and behaves the same as it does today.

**Acceptance Scenarios**:

1. **Given** an authenticated staff member, **When** they create, update, or delete a product, collection, or product image, **Then** the action succeeds through the staff prefix.
2. **Given** an authenticated staff member, **When** they view or manage any customer's order, **Then** the action succeeds through the staff prefix.
3. **Given** an authenticated staff member, **When** they request a report, **Then** the report is served through the staff prefix.
4. **Given** a non-staff (or unauthenticated) caller, **When** they call any staff-prefixed endpoint, **Then** the request is rejected with an authorization error.

---

### User Story 3 - Integrator/developer discovers the API surface (Priority: P3)

A developer integrating with the API (internal team, API docs reader) can tell from the URL alone whether an endpoint is customer-facing or staff-only, without needing to inspect permission classes.

**Why this priority**: Improves clarity and maintainability but does not change runtime behavior for existing users — lowest priority since it's a documentation/structure benefit rather than a functional one.

**Independent Test**: Can be fully tested by reviewing the generated API schema/docs and confirming every endpoint appears under exactly one of the two prefixes, matching its actual permission requirement.

**Acceptance Scenarios**:

1. **Given** the published API schema, **When** a developer looks at any endpoint's path, **Then** the prefix alone (`store-front/` vs `store-admin/`) tells them the required audience/permission level.
2. **Given** the existing set of endpoints under the current single prefix, **When** the split is complete, **Then** every one of them has been placed under exactly one new prefix with no endpoint duplicated or dropped.

---

### Edge Cases

- Requests made to the old single `store/` prefix after the split are simply no longer routed — there are no external consumers to protect, so the old prefix is removed at cutover with no alias/redirect period.
- An endpoint that mixes audiences today (e.g., a review write by a customer, but review moderation/deletion by staff) — how is it split, since "read + a few writes/deletes" for customers and "anything gated by admin" for staff must both be satisfied for the same resource type without gaps or duplication?
- A staff member is also a customer (has their own cart/orders) — do they still use the customer-facing prefix for their own personal shopping, and the staff-only prefix only for admin actions?
- An endpoint currently reachable under the single prefix that isn't explicitly named in the audience lists (e.g., likes, tags, notifications) — which prefix does it land under, based on whether it's gated by admin permission today?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose all customer-facing actions (browse products, browse collections, read/write reviews, manage cart, view/manage own orders, view/manage own customer profile, checkout/payment) under a customer-facing URL prefix.
- **FR-002**: System MUST expose all staff-only actions (create/update/delete products, collections, and product images; manage any customer's orders; view reports; and any other action currently gated by admin permission) under a staff-only URL prefix.
- **FR-003**: System MUST continue to enforce the same permission rules per action after the split as it does today — the split changes URL structure, not who is allowed to do what.
- **FR-004**: System MUST reject staff-only actions requested by non-staff or unauthenticated callers, regardless of which prefix the request arrives on.
- **FR-005**: System MUST NOT expose any endpoint under both prefixes at once, and MUST NOT drop any endpoint that exists today.
- **FR-006**: System MUST update the published API schema/docs so every endpoint is documented under its correct new prefix.
- **FR-007**: System MUST place every currently-existing endpoint (including ones not explicitly named in the customer/staff lists above) under the prefix matching its current permission requirement: admin-gated endpoints go under the staff-only prefix, everything else goes under the customer-facing prefix.
- **FR-008**: For resources that mix audiences (e.g., a customer can create/edit their own review, while staff can moderate/delete any review), System MUST expose the customer-scoped actions under the customer-facing prefix and the staff-scoped actions on the same resource under the staff-only prefix.
- **FR-009**: System MUST remove the old single `store/` prefix at cutover (no redirect/alias period), since there are no external consumers to protect.

### Key Entities

- **Customer-facing action**: An API action available to any authenticated (or anonymous, for browsing) shopper, scoped to their own data where applicable (own cart, own orders, own profile).
- **Staff-only action**: An API action that requires admin/staff permission, and may operate on data across all customers (all orders, all products, reports).
- **Endpoint/resource**: A single API capability (e.g., "list products", "delete a product image") that must be classified into exactly one of the two audience prefixes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of existing API endpoints are reachable under exactly one of the two new audience-based prefixes, with no endpoint missing or duplicated.
- **SC-002**: Every staff-only endpoint rejects non-staff callers 100% of the time, verified by testing each one under the new structure.
- **SC-003**: Existing customer-facing workflows (browse, cart, checkout, own orders, own profile, reviews) complete with the same success rate and behavior as before the split.
- **SC-004**: A developer can correctly guess, from the URL prefix alone, whether an endpoint requires staff permission, for at least 95% of endpoints sampled.
- **SC-005**: API documentation shows zero endpoints still listed under the old single prefix after rollout is complete.

## Assumptions

- The split is a reorganization of the existing API's URL structure and permission grouping; it does not introduce new business capabilities or change what any user role is allowed to do.
- "Anything gated by admin permission today" is the authoritative rule for classifying any endpoint not explicitly named in the customer-facing or staff-only lists.
- Existing authentication mechanism (session/token-based) is reused unchanged; only URL prefixes and endpoint grouping change.
- Staff members who also shop as customers use the customer-facing prefix for their own personal cart/orders/profile, and the staff-only prefix only for admin actions.
- Reports are staff-only and read-only from the API's perspective (no customer-facing reporting).
- The API has no external/third-party consumers to protect; the old `store/` prefix is removed at cutover with no deprecation/alias period.
