from .dawurobo import DawuroboGateway

_PROVIDERS = {
    'DAWUROBO': DawuroboGateway,
}


def get_provider(name):
    """Look up a shipping provider implementation by its Shipment.provider
    value. Add a new provider by registering its class here."""
    try:
        provider_cls = _PROVIDERS[name]
    except KeyError:
        raise ValueError(f'Unknown shipping provider: {name!r}')
    return provider_cls()
