"""
Local development settings.

manage.py / wsgi.py / asgi.py all fall back to this module when
DJANGO_SETTINGS_MODULE isn't set — no env var needed for local runs.
Deployed environments set DJANGO_SETTINGS_MODULE explicitly to
storefront.settings.staging or storefront.settings.prod instead.
"""

import os

from .base import *  # noqa: F401,F403

DEBUG = True

# No real secret needed locally. Falls back to this insecure key when
# SECRET_KEY is unset/blank in .env — never use this value anywhere real.
SECRET_KEY = os.environ.get('SECRET_KEY') or \
    'django-insecure-hs6j037urx6iav+7#10%-vu4l4f5@@-1_zo)oft4g7$vf2$jmp'

# debug_toolbar is dev-only — injects a panel + extra queries on every
# request. Only ever loaded here, never in staging/prod.
INSTALLED_APPS = INSTALLED_APPS + ['debug_toolbar']
MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE

INTERNAL_IPS = [
    '127.0.0.1',
]

# The local Refine dev server(s), on top of whatever CORS_ALLOWED_ORIGINS
# (base.py) is set to.
CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS + [
    'http://localhost:5173',
    'http://localhost:4173',   # Vite default
    'http://localhost:3000',   # CRA/Next default
]

# Cross-site cookies need SameSite=None + Secure, which only works over
# HTTPS — plain local http can't receive them back. Use ngrok (real HTTPS
# tunnel) if you need to test that path locally instead of loosening this.
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = False

# Skip whitenoise's manifest requirement (base.py's STATIC_ROOT still
# works with `runserver`'s own static serving in DEBUG, so this is mostly
# so `collectstatic` doesn't demand a manifest lookup locally).
STORAGES = {
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}
