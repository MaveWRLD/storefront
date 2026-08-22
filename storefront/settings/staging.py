"""
Staging settings.

Selected by setting DJANGO_SETTINGS_MODULE=storefront.settings.staging
on the staging deploy. Deliberately mirrors prod's security posture
(same DEBUG=False, same SECRET_KEY/ALLOWED_HOSTS enforcement, same
whitenoise storage) so staging actually catches prod-only bugs — the
only differences are below, both about not locking browsers onto a
staging domain that may get reassigned or torn down.
"""

from .prod import *  # noqa: F401,F403

SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
