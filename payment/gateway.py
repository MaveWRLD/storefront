"""Paystack gateway calls.

Adapted from Saleor's payment/gateway.py orchestration layer, minus the
plugin-manager abstraction over multiple gateways — this Business Rule
requires Paystack exclusively, so there's only ever one implementation.
"""
import requests
from django.conf import settings

PAYSTACK_BASE_URL = 'https://api.paystack.co'


class PaystackError(Exception):
    """Raised when Paystack's API can't be reached or rejects the request."""


def _headers():
    return {
        'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
        'Content-Type': 'application/json',
    }


def initialize_transaction(email, amount, reference):
    """Start a Paystack transaction. `amount` is in the currency's major
    unit (e.g. dollars); Paystack wants the minor unit (e.g. cents)."""
    response = requests.post(
        f'{PAYSTACK_BASE_URL}/transaction/initialize',
        json={
            'email': email,
            'amount': int(amount * 100),
            'reference': reference,
        },
        headers=_headers(),
        timeout=10,
    )
    data = response.json()
    if not response.ok or not data.get('status'):
        raise PaystackError(data.get('message', 'Could not initialize payment.'))
    return data['data']  # {authorization_url, access_code, reference}


def verify_transaction(reference):
    """Ask Paystack whether a transaction succeeded."""
    response = requests.get(
        f'{PAYSTACK_BASE_URL}/transaction/verify/{reference}',
        headers=_headers(),
        timeout=10,
    )
    data = response.json()
    if not response.ok or not data.get('status'):
        raise PaystackError(data.get('message', 'Could not verify payment.'))
    return data['data']  # includes 'status': 'success' | 'failed' | ...
