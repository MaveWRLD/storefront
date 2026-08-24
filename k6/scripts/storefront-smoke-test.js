import http from 'k6/http';
import { check, group } from 'k6';

// Smoke test: anonymous storefront (non-admin) APIs. Covers the happy path
// AND expected edge-case/error responses (invalid input, missing resources,
// auth-required routes hit anonymously) — a smoke test still only touches
// documented, deterministic behavior, not load/stress.
export const options = {
  scenarios: {
    smoke: {
      executor: 'constant-vus',
      vus: 2,
      duration: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate==0'], // "failed" = transport error; 4xx here are checked responses, not failures
    http_req_duration: ['p(95)<500'], // staging (gunicorn) measured p(95)~173ms; 500ms leaves headroom w/o masking regressions
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const JSON_HEADERS = { headers: { 'Content-Type': 'application/json' } };

// Edge-case groups below deliberately provoke 4xx responses — those are the
// checked, expected outcome, not a transport failure. Without this, k6 would
// count every intentional 4xx against http_req_failed and the threshold above
// would never pass.
http.setResponseCallback(
  http.expectedStatuses(200, 201, 204, 400, 401, 404, 405),
);

export default function () {
  // ---- Happy path -------------------------------------------------------

  group('api root', () => {
    const res = http.get(`${BASE_URL}/store-front/`);
    check(res, {
      'root status is 200': (r) => r.status === 200,
      'root lists products link': (r) => r.json('products') !== undefined,
    });
  });

  group('products list', () => {
    const res = http.get(`${BASE_URL}/store-front/products/`);
    check(res, {
      'products status is 200': (r) => r.status === 200,
      'products body is paginated list': (r) => Array.isArray(r.json('results')),
    });
  });

  group('collections list', () => {
    // CollectionViewSet has no pagination_class -> plain array, not {results: [...]}.
    const res = http.get(`${BASE_URL}/store-front/collections/`);
    check(res, {
      'collections status is 200': (r) => r.status === 200,
      'collections body is a list': (r) => Array.isArray(r.json()),
    });
  });

  group('cart detail (guest session)', () => {
    const res = http.get(`${BASE_URL}/store-front/cart/`);
    check(res, {
      'cart status is 200': (r) => r.status === 200,
      'cart has items array': (r) => Array.isArray(r.json('items')),
    });
  });

  // ---- Edge cases: not-found / bad input ---------------------------------

  group('product detail - nonexistent slug', () => {
    const res = http.get(`${BASE_URL}/store-front/products/does-not-exist-slug/`);
    check(res, { '404 on unknown slug': (r) => r.status === 404 });
  });

  group('products list - search with no matches', () => {
    // Not an error: empty result set, still 200.
    const res = http.get(`${BASE_URL}/store-front/products/?search=zzz_no_such_product_zzz`);
    check(res, {
      'empty search still 200': (r) => r.status === 200,
      'empty search returns empty results': (r) => r.json('results').length === 0,
    });
  });

  group('products list - page out of range', () => {
    const res = http.get(`${BASE_URL}/store-front/products/?page=99999`);
    check(res, { '404 on out-of-range page': (r) => r.status === 404 });
  });

  group('products list - invalid page value', () => {
    const res = http.get(`${BASE_URL}/store-front/products/?page=not-a-number`);
    check(res, { '404 on non-numeric page': (r) => r.status === 404 });
  });

  group('collection detail - nonexistent id', () => {
    const res = http.get(`${BASE_URL}/store-front/collections/999999999/`);
    check(res, { '404 on unknown collection id': (r) => r.status === 404 });
  });

  group('cart items - add nonexistent variant', () => {
    const res = http.post(
      `${BASE_URL}/store-front/cart/items/`,
      JSON.stringify({ variant_id: 999999999, quantity: 1 }),
      JSON_HEADERS,
    );
    check(res, { '400 on unknown variant_id': (r) => r.status === 400 });
  });

  group('cart items - add with missing fields', () => {
    const res = http.post(
      `${BASE_URL}/store-front/cart/items/`,
      JSON.stringify({}),
      JSON_HEADERS,
    );
    check(res, { '400 on missing variant_id': (r) => r.status === 400 });
  });

  group('cart items - update nonexistent item', () => {
    const res = http.patch(
      `${BASE_URL}/store-front/cart/items/999999999/`,
      JSON.stringify({ quantity: 2 }),
      JSON_HEADERS,
    );
    check(res, { '404 on unknown cart item': (r) => r.status === 404 });
  });

  group('disallowed method on products list', () => {
    const res = http.del(`${BASE_URL}/store-front/products/`);
    check(res, { '405 on DELETE to list endpoint': (r) => r.status === 405 });
  });

  // ---- Edge cases: auth-required routes hit anonymously ------------------

  group('customer profile - anonymous', () => {
    const res = http.get(`${BASE_URL}/store-front/customers/me/`);
    check(res, { '401 for anonymous profile access': (r) => r.status === 401 });
  });

  group('orders list - anonymous', () => {
    const res = http.get(`${BASE_URL}/store-front/orders/`);
    check(res, { '401 for anonymous order list': (r) => r.status === 401 });
  });

  group('payment initialize - nonexistent order, no guest token', () => {
    const res = http.post(
      `${BASE_URL}/store-front/payments/initialize/`,
      JSON.stringify({ order_id: 999999999 }),
      JSON_HEADERS,
    );
    check(res, { '400 on unknown order_id': (r) => r.status === 400 });
  });
}
