"""
Staging settings.

Selected by setting DJANGO_SETTINGS_MODULE=storefront.settings.staging
on the staging deploy. Deliberately mirrors prod's security posture
(same DEBUG=False, same SECRET_KEY/ALLOWED_HOSTS enforcement, same
whitenoise storage) so staging actually catches prod-only bugs — the
differences below are deliberate exceptions: HSTS, so browsers don't
lock onto a staging domain that may get reassigned or torn down, and
the browsable API, useful for manually poking the staging deploy.
"""

from .prod import *  # noqa: F401,F403

SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# prod.py strips this down to JSON-only; staging keeps DRF's default
# (JSONRenderer + BrowsableAPIRenderer) so it's easy to poke endpoints by
# hand in a browser. Still behind whatever auth each view already requires.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),
}
