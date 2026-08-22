"""Dawurobo provider implementation.

Dawurobo is an Accra-based delivery network (intracity + nationwide
across Ghana's major cities) already integrated by Ghanaian e-commerce
platforms (e.g. Catlog) — see research.md §1 for why it replaced the
original Nigeria-market Shipbubble choice once Ghana coverage mattered.

Verified against docs.dawurobo.com's published OpenAPI spec, guide
pages, and live sandbox calls (2026-08-19) — endpoints, request-signing
recipe, request/response field names, and webhook payload shape below
are the real contract:
https://docs.dawurobo.com/docs/authentication-and-signing
https://docs.dawurobo.com/docs/delivery-orders
https://docs.dawurobo.com/docs/webhooks

Note: `orders.estimate` returns a `priority` tier list (standard/
economy/cargo, each its own price) but `orders.create`'s request
schema has no `priority` field at all — a tier shown at quote time
can't actually be booked. `get_rates` surfaces the tiers as read-only
`options` for customer transparency; the headline `estimated_price` is
what's charged and what `orders.create` will actually honor.
"""
import hashlib
import hmac
import json
import time
import uuid

import requests
from django.conf import settings

from .base import ShippingProvider, ShippingProviderError

DAWUROBO_BASE_URL = 'https://delivery.dawurobo.com'
_EMPTY_BODY_SHA256 = hashlib.sha256(b'').hexdigest()


class DawuroboGateway(ShippingProvider):
    def _sign(self, method, path, query, body_bytes, timestamp, nonce):
        """HMAC-SHA256 over the exact canonical string Dawurobo expects:
        METHOD\\nPATHNAME\\nQUERY\\nSHA256_BODY\\nTIMESTAMP\\nNONCE
        — signed with the signing secret (`DAWUROBO_SIGNING_SECRET`).
        In practice Dawurobo issues one key used as both the API key
        and the signing secret — DAWUROBO_API_KEY and
        DAWUROBO_SIGNING_SECRET may be the same value.
        """
        body_hash = (
            hashlib.sha256(body_bytes).hexdigest() if body_bytes else _EMPTY_BODY_SHA256)
        canonical = '\n'.join([
            method.upper(), path, query or '', body_hash, timestamp, nonce,
        ])
        return hmac.new(
            settings.DAWUROBO_SIGNING_SECRET.encode(), canonical.encode(), hashlib.sha256,
        ).hexdigest()

    def _request(self, method, path, json_body=None):
        """Shared request/signing/error-wrapping so a network failure
        (timeout, connection refused, DNS, ...) surfaces as a
        `ShippingProviderError` just like a rejected response does —
        callers (e.g. `shipping.services.book_shipment_for_order`) only
        ever need to handle one exception type (FR-010)."""
        body_bytes = json.dumps(json_body).encode() if json_body is not None else b''
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        signature = self._sign(method, path, '', body_bytes, timestamp, nonce)
        headers = {
            'Content-Type': 'application/json',
            'X-API-Key': settings.DAWUROBO_API_KEY,
            'X-Signature': signature,
            'X-Timestamp': timestamp,
            'X-Nonce': nonce,
        }
        try:
            response = requests.request(
                method, f'{DAWUROBO_BASE_URL}{path}',
                data=body_bytes if json_body is not None else None,
                headers=headers, timeout=10)
        except requests.exceptions.RequestException as e:
            raise ShippingProviderError(f'Could not reach the shipping provider: {e}')
        try:
            data = response.json()
        except ValueError:
            raise ShippingProviderError('The shipping provider returned an unreadable response.')
        return response, data

    def _pickup_location(self):
        """Dawurobo defaults pickup to central Accra when omitted
        (docs.dawurobo.com/docs/delivery-orders) — only send it once
        real warehouse coordinates are configured."""
        if settings.DAWUROBO_PICKUP_LAT and settings.DAWUROBO_PICKUP_LNG:
            return {
                'coordinates': {
                    'lat': float(settings.DAWUROBO_PICKUP_LAT),
                    'lng': float(settings.DAWUROBO_PICKUP_LNG),
                },
            }
        return None

    def get_rates(self, order, address):
        body = {'delivery_location': {'coordinates': address['coordinates']}}
        if address.get('street_address'):
            body['delivery_location']['address'] = address['street_address']
        pickup = self._pickup_location()
        if pickup:
            body['pickup_location'] = pickup

        response, data = self._request('post', '/api/v1/delivery/orders.estimate', body)
        if not response.ok or data.get('status') != 'success':
            raise ShippingProviderError(
                data.get('message', 'Could not fetch a shipping estimate for this address.'))
        estimate = data['data']
        if not estimate.get('location_coverage', {}).get('delivery_available', True):
            raise ShippingProviderError('Delivery is not available for this address.')
        return {
            'cost': estimate['estimated_price'],
            'estimated_delivery_at': estimate.get('estimated_delivery_time'),
            # Informational only — orders.create has no `priority` field
            # to honor one of these, see module docstring.
            'options': [
                {'priority': o['priority'], 'cost': o['price'], 'description': o.get('description', '')}
                for o in estimate.get('available_options', [])
            ],
        }

    def _recipient_contact(self, order, address):
        # `address` (Order.shipping_address) is the sole contact record
        # for a guest order; an authenticated customer who didn't
        # override it falls back to their account.
        name = address.get('recipient_name', '')
        phone = address.get('phone', '')
        if not name and order.customer_id:
            name = f'{order.customer.user.first_name} {order.customer.user.last_name}'.strip()
        if not phone and order.customer_id:
            phone = order.customer.phone
        return name or 'Customer', phone

    def create_shipment(self, order, address):
        name, phone = self._recipient_contact(order, address)
        body = {
            'order_reference': f'order-{order.pk}-{uuid.uuid4().hex[:8]}',
            'customer': {'name': name, 'phone': phone},
            'delivery': {
                'address': address.get('street_address', ''),
                'city': address.get('city', ''),
                'region': address.get('region', ''),
                'coordinates': address['coordinates'],
            },
            'item': ', '.join(
                item.variant.product.title for item in
                order.items.select_related('variant__product')),
            'pickup': {
                'contact_person': settings.DAWUROBO_PICKUP_CONTACT_NAME,
                'contact_phone': settings.DAWUROBO_PICKUP_CONTACT_PHONE,
            },
            # We already collected the delivery fee from the customer
            # via Paystack (Order.shipping_cost, folded into get_total())
            # at checkout — settle with Dawurobo from our own wallet
            # rather than cash-on-delivery from the recipient again.
            # Requires the delivery:wallet:spend scope and a funded
            # sandbox/production wallet; returns 402 if insufficient.
            'payment': {'payer': 'partner'},
        }
        pickup = self._pickup_location()
        if pickup:
            body['pickup']['coordinates'] = pickup['coordinates']

        response, data = self._request('post', '/api/v1/delivery/orders.create', body)
        if not response.ok or data.get('status') != 'success':
            raise ShippingProviderError(
                data.get('message', 'Could not book this shipment.'))
        order_details = data['data']['order_details']
        return {
            'tracking_reference': order_details['order_id'],
            'estimated_delivery_at': order_details.get('estimated_delivery'),
        }

    def get_shipment(self, tracking_reference):
        response, data = self._request(
            'post', '/api/v1/delivery/orders.get', {'order_id': tracking_reference})
        if not response.ok or data.get('status') != 'success':
            raise ShippingProviderError(
                data.get('message', 'Could not fetch this shipment\'s status.'))
        return data['data']  # includes 'status'

    def verify_webhook_signature(self, body, signature):
        """Dawurobo signs webhook bodies with HMAC-SHA256 keyed on the
        webhook secret, over the raw JSON body — an unauthenticated POST
        must never be trusted as a real shipment-status update (FR-008)."""
        if not signature:
            return False
        expected = hmac.new(
            settings.DAWUROBO_WEBHOOK_SECRET.encode(), body, hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
