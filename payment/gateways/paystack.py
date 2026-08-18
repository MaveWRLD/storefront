"""Paystack gateway implementation.

Adapted from Saleor's payment/gateway.py orchestration layer, minus the
plugin-manager abstraction over multiple gateways — this class is the
Paystack side of that abstraction now that `PaymentGateway` (base.py)
carries the interface and more gateways can be added alongside it.
"""
import hashlib
import hmac

import requests
from django.conf import settings

from .base import PaymentGateway, PaymentGatewayError

PAYSTACK_BASE_URL = 'https://api.paystack.co'


class PaystackGateway(PaymentGateway):
    def _headers(self):
        return {
            'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json',
        }

    def initialize_transaction(self, email, amount, reference):
        response = requests.post(
            f'{PAYSTACK_BASE_URL}/transaction/initialize',
            json={
                'email': email,
                'amount': int(amount * 100),
                'reference': reference,
            },
            headers=self._headers(),
            timeout=10,
        )
        data = response.json()
        if not response.ok or not data.get('status'):
            raise PaymentGatewayError(data.get('message', 'Could not initialize payment.'))
        return data['data']  # {authorization_url, access_code, reference}

    def verify_transaction(self, reference):
        response = requests.get(
            f'{PAYSTACK_BASE_URL}/transaction/verify/{reference}',
            headers=self._headers(),
            timeout=10,
        )
        data = response.json()
        if not response.ok or not data.get('status'):
            raise PaymentGatewayError(data.get('message', 'Could not verify payment.'))
        return data['data']  # includes 'status': 'success' | 'failed' | ...

    def verify_webhook_signature(self, body, signature):
        """Paystack signs webhook bodies with HMAC-SHA512 keyed on the
        secret key (P1: webhook is the reconciliation safety net, so an
        unauthenticated POST must never be trusted as a real event)."""
        if not signature:
            return False
        expected = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode(), body, hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def refund_transaction(self, reference):
        """Business Rule (Returns & Refunds): 'Rejected return: item back
        to customer, no refund; approved: Paystack refund' — full refund
        of the original transaction, no partial-amount support (single
        item per order in this domain's simplified scope)."""
        response = requests.post(
            f'{PAYSTACK_BASE_URL}/refund',
            json={'transaction': reference},
            headers=self._headers(),
            timeout=10,
        )
        data = response.json()
        if not response.ok or not data.get('status'):
            raise PaymentGatewayError(data.get('message', 'Could not issue refund.'))
        return data['data']
