"""
Django settings shared by every environment.

dev.py / staging.py / prod.py each `from .base import *` and layer on
their own DEBUG, SECRET_KEY, security, and storage choices. Which one
actually loads is picked by DJANGO_SETTINGS_MODULE — see manage.py,
storefront/wsgi.py, storefront/asgi.py (default to dev) and Railway's
env vars (set to storefront.settings.staging or storefront.settings.prod).

For more information on this file, see
https://docs.djangoproject.com/en/3.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.2/ref/settings/
"""

import os
from pathlib import Path
from datetime import timedelta

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# One extra .parent vs the old single-file settings.py — this module now
# lives at storefront/settings/base.py, not storefront/settings.py.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

ALLOWED_HOSTS = [
    h for h in os.environ.get('ALLOWED_HOSTS', '').split(',') if h
]
# ngrok's forwarding domain must be added here to test webhooks locally
# (DEBUG's implicit localhost/127.0.0.1 allowance doesn't cover it) — e.g.
# ALLOWED_HOSTS=abcd1234.ngrok-free.app

# Sentry — no-op locally when SENTRY_DSN isn't set, so dev/CI never need it.
SENTRY_DSN = os.environ.get('SENTRY_DSN')
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        # DJANGO_SETTINGS_MODULE's last segment (dev/staging/prod) doubles
        # as the Sentry environment tag unless SENTRY_ENVIRONMENT overrides it.
        environment=os.environ.get(
            'SENTRY_ENVIRONMENT',
            os.environ.get('DJANGO_SETTINGS_MODULE', '').rsplit('.', 1)[-1] or 'unknown',
        ),
        # Fraction of requests sent to Performance/Tracing — 0.2 keeps
        # volume/cost sane while still giving latency breakdowns. Errors
        # are always captured regardless of this rate.
        traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0.2')),
        send_default_pii=False,
    )


# Application definition

INSTALLED_APPS = [
    'django_prometheus',
    'django.contrib.admin',
    'django.contrib.sessions',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_filters',
    'rest_framework',
    'drf_spectacular',
    'djoser',
    'corsheaders',
    'djmoney',
    'catalog',
    'media_storage',
    'customers',
    'cart',
    'orders',
    'payment',
    'shipping',
    'returns',
    'notifications',
    'reports',
    'tags',
    'likes',
    'core',
]

MIDDLEWARE = [
    # Must be first — starts the per-request timer django-prometheus uses
    # to record request latency (paired with PrometheusAfterMiddleware,
    # which must be last).
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # Serves collected static files directly from gunicorn — no separate
    # static host needed for admin/DRF-browsable-API/spectacular assets.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]

# CORS: the deployed frontend origin(s) — comma-separated, e.g.
# CORS_ALLOWED_ORIGINS=https://app.apparelfit.fashion
# dev.py appends the local Vite/CRA dev server origins on top of this.
# Do not use CORS_ALLOW_ALL_ORIGINS in production.
CORS_ALLOWED_ORIGINS = [
    o for o in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',') if o
]
CORS_ALLOW_CREDENTIALS = True
# Cache preflight (OPTIONS) responses in the browser so repeat requests
# skip the extra round trip. 86400s = 24h (Chrome's own cap on this value).
CORS_PREFLIGHT_MAX_AGE = 86400

ROOT_URLCONF = 'storefront.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'storefront.wsgi.application'


# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME') or 'storefront',
        'HOST': os.environ.get('DB_HOST') or 'localhost',
        'PORT': os.environ.get('DB_PORT') or '5433',
        'USER': os.environ.get('DB_USER') or 'postgres',
        'PASSWORD': os.environ.get('DB_PASSWORD') or 'testpass',
    }
}


# Password validation
# https://docs.djangoproject.com/en/3.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.2/howto/static-files/

STATIC_URL = '/static/'
# collectstatic target — whitenoise middleware serves from here in
# staging/prod; dev.py swaps STORAGES to skip the manifest requirement.
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Product images (US-02). No object-storage integration yet (that's a
# separate infra concern) — local media storage for now.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Product images (US-02): pluggable storage — 'local' (default, no creds
# needed) or 'r2' (Cloudflare R2). See media_storage app.
# Deployment note: the 'r2' backend needs six env vars set (R2_BUCKET_NAME,
# R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_PUBLIC_DOMAIN,
# and optionally R2_REGION, default 'auto'). Either backend also needs the
# system `libmagic` library installed (python-magic wraps it) — on
# Debian/Ubuntu: `apt-get install -y libmagic1`. Without it, `import magic`
# fails at Django startup (media_storage.services.upload is imported by
# catalog.serializers at module load time).
MEDIA_STORAGE_BACKEND = os.environ.get('MEDIA_STORAGE_BACKEND', 'local')

if MEDIA_STORAGE_BACKEND == 'r2':
    CLOUDFLARE_R2 = {
        'BUCKET_NAME': os.environ['R2_BUCKET_NAME'],
        'REGION': os.environ.get('R2_REGION', 'auto'),
        'ENDPOINT': os.environ['R2_ENDPOINT'],
        'ACCESS_KEY_ID': os.environ['R2_ACCESS_KEY_ID'],
        'SECRET_ACCESS_KEY': os.environ['R2_SECRET_ACCESS_KEY'],
        'PUBLIC_DOMAIN': os.environ['R2_PUBLIC_DOMAIN'],
    }

# Default primary key field type
# https://docs.djangoproject.com/en/3.2/ref/settings/#default-auto-field

# Without this, an uncaught 500 (django.request logger) goes nowhere —
# no console handler is configured by default outside runserver/DEBUG.
# Gunicorn's own stdout/stderr becomes the traceback destination here,
# which is what Railway's log viewer actually shows.
# Ships logs to Grafana Cloud via OTLP — same OTEL_EXPORTER_OTLP_ENDPOINT/
# OTEL_EXPORTER_OTLP_HEADERS already used for metrics/traces (Procfile's
# opentelemetry-instrument wrapper), no separate Loki credentials needed.
# No-op locally when OTEL_EXPORTER_OTLP_ENDPOINT isn't set.
_log_handlers = ['console']
_LOGGING_HANDLERS = {
    'console': {
        'class': 'logging.StreamHandler',
    },
}
if os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT'):
    _LOGGING_HANDLERS['otel'] = {
        '()': 'storefront.observability.get_otel_log_handler',
    }
    _log_handlers.append('otel')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': _LOGGING_HANDLERS,
    'root': {
        'handlers': _log_handlers,
        'level': 'INFO',
    },
    'loggers': {
        'django.request': {
            'handlers': _log_handlers,
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'COERCE_DECIMAL_TO_STRING': False,
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # IP-keyed, matching the Spring reference (gap-analysis doc: 'No rate
    # limiting anywhere'). Applied per-view via ScopedRateThrottle +
    # throttle_scope, not blanket DEFAULT_THROTTLE_CLASSES — only
    # login/register and guest order lookup need it.
    'DEFAULT_THROTTLE_RATES': {
        'auth': '5/min',
        'order-lookup': '20/min',
        'payment': '20/min',
    },
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'ApparelFit API',
    'DESCRIPTION': 'Storefront API for ApparelFit.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

AUTH_USER_MODEL = 'core.User'

DJOSER = {
    'SERIALIZERS': {
        'user_create': 'core.serializers.UserCreateSerializer',
        'current_user': 'core.serializers.UserSerializer',
    }
}

SIMPLE_JWT = {
    'AUTH_HEADER_TYPES': ('JWT',),
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1)
}

# Guest cart identity: cart_id is the only thing the session carries, so
# storing it in the signed cookie itself (rather than the django_session
# table) skips a DB round-trip on every cart-touching request. Signed, not
# encrypted — never put anything sensitive in request.session.
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'

# django-money
DEFAULT_CURRENCY = 'GHS'
CURRENCIES = ('GHS',)

# Cart (US-12, Business Rule: 'Abandoned checkout preserves the cart') —
# a cart is only expired after this many days without activity (Cart.last_activity).
# Single flat TTL, not Saleor's anonymous/user/empty-cart split (no auth-tied
# checkout ownership in this domain yet).
CART_ABANDONMENT_TTL_DAYS = 30

# Payment (Business Rule: 'Checkout/payment session expiry' — payment
# abandonAfter 1 hour): a Paystack transaction left PENDING this long is
# considered abandoned. Doesn't block retrying (US-11 has no retry cap) —
# just stops treating a stale attempt as still in flight.
PAYMENT_ABANDON_AFTER_MINUTES = 60

# Payment (US-10): Paystack is the only gateway (Business Rule: 'All payments
# exclusively via Paystack'). Set a real key via env var in every real
# environment; blank locally just means initialize/verify calls will fail
# until one is configured.
PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', '')

# Shipping (004-shipping-integration): Dawurobo (Ghana courier network) is
# the only provider so far, wired up the same way Paystack is above. Blank
# locally just means rate-quote/booking calls will fail until real
# credentials are configured.
DAWUROBO_API_KEY = os.environ.get('DAWUROBO_API_KEY', '')
# Every outgoing request is HMAC-SHA256-signed (docs.dawurobo.com/docs/
# authentication-and-signing). Confirmed against the real sandbox
# (2026-08-19): Dawurobo issues one key used as both the API key and the
# signing secret — DAWUROBO_SIGNING_SECRET is typically the same value
# as DAWUROBO_API_KEY, not a separate `sk_...` secret as their docs text
# implies. DAWUROBO_WEBHOOK_SECRET below is a third, unrelated secret,
# used only to verify incoming webhook signatures.
DAWUROBO_SIGNING_SECRET = os.environ.get('DAWUROBO_SIGNING_SECRET', '')
DAWUROBO_WEBHOOK_SECRET = os.environ.get('DAWUROBO_WEBHOOK_SECRET', '')
# Pickup coordinates omitted (None) below default to Dawurobo's own
# central-Accra default (docs.dawurobo.com/docs/delivery-orders) — set
# real warehouse coordinates here before going live.
DAWUROBO_PICKUP_LAT = os.environ.get('DAWUROBO_PICKUP_LAT') or None
DAWUROBO_PICKUP_LNG = os.environ.get('DAWUROBO_PICKUP_LNG') or None
# REQUIRED by orders.create (no default from Dawurobo) — the warehouse's
# own contact name/phone, not the customer's. Placeholders below WILL
# cause real bookings to use fake contact info; replace before any
# create_shipment call that isn't purely a sandbox smoke test.
DAWUROBO_PICKUP_CONTACT_NAME = os.environ.get('DAWUROBO_PICKUP_CONTACT_NAME', 'Warehouse')
DAWUROBO_PICKUP_CONTACT_PHONE = os.environ.get('DAWUROBO_PICKUP_CONTACT_PHONE', '+233000000000')
