import os

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self) -> None:
        import core.signals.handlers

        # No-op locally when OTEL_EXPORTER_OTLP_ENDPOINT isn't set — same
        # gate as the log handler in storefront/observability.py.
        if os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT'):
            from storefront.observability import instrument_system_metrics
            instrument_system_metrics()