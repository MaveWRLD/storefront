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

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource


def get_otel_log_handler():
    resource = Resource.create({
        'service.name': os.environ.get('OTEL_SERVICE_NAME', 'storefront'),
    })
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    return LoggingHandler(level=logging.NOTSET, logger_provider=provider)
