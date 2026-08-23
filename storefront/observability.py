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

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource


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


