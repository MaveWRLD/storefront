import pytest

from shipping.gateways import get_provider
from shipping.gateways.dawurobo import DawuroboGateway


class TestProviderFactory:
    def test_get_provider_returns_dawurobo_implementation(self):
        provider = get_provider('DAWUROBO')

        assert isinstance(provider, DawuroboGateway)

    def test_get_provider_raises_on_unknown_name(self):
        with pytest.raises(ValueError):
            get_provider('DHL')
