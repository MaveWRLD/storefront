"""Payment gateway interface — every gateway implementation conforms to
this so `payment/serializers.py` and `payment/views.py` can work against
any of them without knowing which one they're calling."""
from abc import ABC, abstractmethod


class PaymentGatewayError(Exception):
    """Raised when a payment gateway's API can't be reached or rejects the request."""


class PaymentGateway(ABC):
    @abstractmethod
    def initialize_transaction(self, email, amount, reference):
        """Start a transaction. `amount` is in the currency's major unit
        (e.g. dollars). Returns a dict including `authorization_url`."""

    @abstractmethod
    def verify_transaction(self, reference):
        """Ask the gateway whether a transaction succeeded. Returns a
        dict including `status`: `'success'` | `'failed'` | ..."""

    @abstractmethod
    def verify_webhook_signature(self, body, signature):
        """Check a webhook request's signature against the raw body."""

    @abstractmethod
    def refund_transaction(self, reference):
        """Issue a full refund of a previously successful transaction."""
