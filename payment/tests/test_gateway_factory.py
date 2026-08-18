import pytest

from payment.gateways import get_gateway
from payment.gateways.paystack import PaystackGateway


class TestGatewayFactory:
    def test_get_gateway_returns_paystack_implementation(self):
        gateway = get_gateway('PAYSTACK')

        assert isinstance(gateway, PaystackGateway)

    def test_get_gateway_raises_on_unknown_name(self):
        with pytest.raises(ValueError):
            get_gateway('STRIPE')
