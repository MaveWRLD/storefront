from django.conf import settings
from .services import CART_SESSION_KEY


def bind_client_to_cart(client, cart):
    """Point a guest APIClient's session at an already-created Cart, the way
    a real request would after cart/services.get_or_create_cart first
    stashed that id — for tests that build a Cart via the ORM directly and
    then need the API to resolve back to that same row."""
    session = client.session
    session[CART_SESSION_KEY] = str(cart.id)
    session.save()
    client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
