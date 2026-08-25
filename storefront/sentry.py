"""Sentry error reporting.

Errors only — tracing and metrics stay with OpenTelemetry (see
`opentelemetry-instrument` in start.sh). Two observability backends both
sampling spans would double the instrumentation cost and split the same
request across two UIs, so `traces_sample_rate` is left at 0 and Sentry
is used purely as the exception/error-log sink OTel doesn't provide.

Initialised from settings/base.py rather than lazily, because Sentry has
to be running before Django imports the app modules it patches. A missing
SENTRY_DSN disables it silently, which is what local dev wants.
"""

import logging
import os

import sentry_sdk
from django.core.exceptions import DisallowedHost
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

logger = logging.getLogger(__name__)


def _tag_otel_trace(event: dict, hint: dict) -> dict:
    """Stamp the active OTel trace/span id onto the event.

    Lets a Sentry issue be pasted straight into Tempo to get the full
    request trace. Sentry's own trace ids are unrelated to OTel's, so
    without this the two backends can't be correlated at all.

    Never raises: a broken before_send hook drops the error report, which
    is strictly worse than an untagged one.
    """
    try:
        from opentelemetry import trace

        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            tags = event.setdefault('tags', {})
            tags['otel.trace_id'] = format(span_context.trace_id, '032x')
            tags['otel.span_id'] = format(span_context.span_id, '016x')
    except Exception:  # pragma: no cover - defensive
        logger.warning('Failed to tag Sentry event with OTel trace context',
                       exc_info=True)
    return event


def init_sentry() -> None:
    """Configure Sentry if SENTRY_DSN is set, otherwise do nothing."""
    dsn = os.environ.get('SENTRY_DSN')
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        # Mirrors OTEL_RESOURCE_ATTRIBUTES' deployment.environment so the
        # same deploy is filterable by the same name in both tools.
        environment=os.environ.get('SENTRY_ENVIRONMENT', 'unknown'),
        # Railway injects the commit sha; lets Sentry attribute a
        # regression to a deploy and mark issues as resolved-in-release.
        release=os.environ.get('RAILWAY_GIT_COMMIT_SHA'),
        integrations=[
            DjangoIntegration(),
            # Breadcrumbs from INFO and above, events only from ERROR —
            # base.py's LOGGING already sends those to stdout for Railway.
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        ],
        # OTel owns tracing. Non-zero here would produce a second,
        # unrelated set of spans for every request.
        traces_sample_rate=0.0,
        # This is a storefront: request bodies carry addresses, order
        # contents and payment references, and headers carry JWTs.
        # Neither belongs in an error tracker.
        send_default_pii=False,
        max_request_body_size='never',
        # Bot probes with a bogus Host header raise this by the hundreds
        # (staging's http.server metrics are almost entirely such 404s).
        # It's an ALLOWED_HOSTS config signal, not an application error.
        ignore_errors=[DisallowedHost],
        before_send=_tag_otel_trace,
    )
