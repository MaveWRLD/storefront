"""Shipping provider interface — every provider implementation conforms
to this so `shipping/serializers.py` and `shipping/services.py` can work
against any of them without knowing which one they're calling.

Mirrors `payment/gateways/base.py`'s ABC + factory pattern (the shape
this app was explicitly asked to reuse), one level up the fulfillment
chain: instead of charging a customer, a provider here quotes and books
a courier for a delivery-method order.

Note: unlike `PaymentGateway` (Paystack hosts a checkout page, one
gateway per Payment attempt with a client-chosen reference), Dawurobo
*is* the courier rather than a multi-courier aggregator — `get_rates`
returns one price/ETA, not a list to choose from, so there's no
"provider_option_id" carried from quote to booking.
"""
from abc import ABC, abstractmethod


class ShippingProviderError(Exception):
    """Raised when a shipping provider's API can't be reached or rejects the request."""


class ShippingProvider(ABC):
    @abstractmethod
    def get_rates(self, order, address):
        """Ask the provider for a live delivery price/ETA for `order`'s
        items, delivered to `address` (a plain dict — at minimum
        `coordinates: {lat, lng}`). Returns a dict with at least
        `cost` (major-unit Decimal-able amount) and
        `estimated_delivery_at`.

        Raises `ShippingProviderError` if the address can't be served
        or the provider can't be reached.
        """

    @abstractmethod
    def create_shipment(self, order, address):
        """Book delivery of `order` to `address` (same shape as
        `get_rates`'s). The fee is always server-priced at booking
        time — this doesn't reuse a quote token from `get_rates`.
        Returns a dict with at least `tracking_reference` and
        `estimated_delivery_at`.

        Raises `ShippingProviderError` if booking fails (address
        rejected, provider unreachable, ...).
        """

    @abstractmethod
    def get_shipment(self, tracking_reference):
        """Ask the provider for a shipment's current status. Returns a
        dict including `status`."""

    @abstractmethod
    def verify_webhook_signature(self, body, signature):
        """Check a webhook request's signature against the raw body."""
