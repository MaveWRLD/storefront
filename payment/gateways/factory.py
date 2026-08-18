from .paystack import PaystackGateway

_GATEWAYS = {
    'PAYSTACK': PaystackGateway,
}


def get_gateway(name):
    """Look up a payment gateway implementation by its Payment.gateway
    value. Add a new gateway by registering its class here."""
    try:
        gateway_cls = _GATEWAYS[name]
    except KeyError:
        raise ValueError(f'Unknown payment gateway: {name!r}')
    return gateway_cls()
