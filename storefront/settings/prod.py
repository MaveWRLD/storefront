"""
Production settings.

Selected by setting DJANGO_SETTINGS_MODULE=storefront.settings.prod on
the deployed host (e.g. Railway service variables). DEBUG is hardcoded
False here, not env-driven — a stray DEBUG=True in prod's env vars can't
flip this on by accident.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False

SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured(
        'SECRET_KEY must be set via env var in prod — refusing to fall '
        'back to the insecure dev key here.'
    )

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured('ALLOWED_HOSTS must be set via env var in prod.')

# DRF's BrowsableAPIRenderer is on by default (base.py doesn't override
# DEFAULT_RENDERER_CLASSES) — HTML forms/login for every endpoint,
# fine in dev, not something to expose in prod. JSON only here.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
}

# whitenoise needs collectstatic's manifest to fingerprint/cache-bust
# assets — dev.py uses the plain filesystem storage instead.
STORAGES = {
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Railway (and most PaaS) terminate TLS at the edge and proxy plain HTTP
# internally — without this header Django thinks every request is
# insecure and SECURE_SSL_REDIRECT below loops forever.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 7  # 1 week; raise once confirmed stable
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cross-origin frontend (CORS_ALLOW_CREDENTIALS=True, base.py) needs the
# sessionid cookie sent on credentialed cross-site requests. SameSite=None
# requires Secure — only works over HTTPS, guaranteed here by
# SECURE_SSL_REDIRECT above.
SESSION_COOKIE_SAMESITE = 'None'
SESSION_COOKIE_SECURE = True
