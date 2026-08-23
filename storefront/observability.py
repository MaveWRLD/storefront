"""
OTLP log handler factory, wired into LOGGING via dictConfig's '()' factory
key (settings/base.py) instead of a plain 'class' entry — building an
OTel LoggingHandler needs a LoggerProvider + exporter constructed first,
not just kwargs passed straight to a constructor.

OTLPLogExporter() takes no args here on purpose: it reads
OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_EXPORTER_OTLP_HEADERS from the
environment itself (appending /v1/logs), same two vars already used for
metrics/traces — one set of Grafana Cloud OTLP credentials for all three
signals, no separate Loki user/key.
"""
import logging
import os
import random

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import View
from opentelemetry.sdk.resources import Resource

# http.server.* series carry these plus a handful of constant-valued keys
# (http_flavor, http_scheme, http_server_name, net_host_port, ...) that
# never differ across this deployment. OTLP repeats the full attribute set
# on every histogram datapoint (not once per series), so dropping the dead
# weight here cuts payload size directly — see configure_metrics().
_HTTP_SERVER_KEPT_ATTRS = {'http_method', 'http_target', 'http_status_code'}


class LogSamplingFilter(logging.Filter):
    """Drops a random fraction of sub-WARNING records before OTLP export.

    Mirrors the Sentry traces_sample_rate pattern: WARNING+ is always kept
    (errors/warnings are cheap in volume and too valuable to drop), only
    INFO/DEBUG noise gets sampled down to keep export volume/cost sane.
    """

    def __init__(self, sample_rate):
        super().__init__()
        self.sample_rate = sample_rate

    def filter(self, record):
        if record.levelno >= logging.WARNING:
            return True
        return random.random() < self.sample_rate


def get_otel_log_handler():
    resource = Resource.create({
        'service.name': os.environ.get('OTEL_SERVICE_NAME', 'storefront'),
    })
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=provider)
    sample_rate = float(os.environ.get('OTEL_LOGS_SAMPLE_RATE', '0.1'))
    handler.addFilter(LogSamplingFilter(sample_rate))
    return handler


def configure_metrics():
    """Installs our own MeterProvider instead of the default one
    opentelemetry-instrument would otherwise build — same reason the log
    handler above is hand-built rather than auto-configured. Needed to
    attach the attribute-trimming View on http.server.* (see
    _HTTP_SERVER_KEPT_ATTRS); auto-instrumentation exposes no env var for
    that.

    Requires OTEL_METRICS_EXPORTER=none (set in Procfile) so
    opentelemetry-instrument's own setup doesn't claim the global
    MeterProvider first — metrics.set_meter_provider() only takes effect
    on the first call, every later call is ignored (with a warning).
    Export interval still comes from OTEL_METRIC_EXPORT_INTERVAL
    (PeriodicExportingMetricReader reads it itself when not passed
    explicitly), so that env var keeps working unchanged.
    """
    resource = Resource.create({
        'service.name': os.environ.get('OTEL_SERVICE_NAME', 'storefront'),
    })
    trim_attrs = {'attribute_keys': _HTTP_SERVER_KEPT_ATTRS}
    views = [
        View(instrument_name='http.server.duration', **trim_attrs),
        View(instrument_name='http.server.active_requests', **trim_attrs),
    ]
    reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    provider = MeterProvider(resource=resource, metric_readers=[reader], views=views)
    metrics.set_meter_provider(provider)


def instrument_system_metrics():
    """Emits process CPU/memory/GC/network metrics (jvm.* equivalent for
    Python) via the MeterProvider configure_metrics() installed. Call once
    per worker process, from an AppConfig.ready() — safe to call multiple
    times only because Django guards ready() against double-invocation
    itself, so no re-entrancy guard is needed here.
    """
    SystemMetricsInstrumentor().instrument()
