"""Manual log-sampling hook for OpenTelemetry.

`start.sh` runs the app under `opentelemetry-instrument`, which auto-configures
traces/metrics/logs from OTEL_* env vars before any Django code loads. There is
no standard `OTEL_LOGS_SAMPLER` env var (log-record sampling isn't part of the
stable OTel spec yet), so we do it manually here: attach a sampling
LogRecordProcessor to the LoggerProvider that `opentelemetry-instrument`
already created.

Requires OTEL_LOGS_EXPORTER to be UNSET (not "otlp") in the environment, so
auto-instrumentation doesn't also attach its own unsampled OTLPLogExporter —
otherwise every log record exports twice, once sampled and once not.
"""

import os
import random

from opentelemetry._logs import get_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor


class SamplingBatchLogRecordProcessor(BatchLogRecordProcessor):
    """BatchLogRecordProcessor that randomly drops records before queuing."""

    def __init__(self, exporter, sample_rate=1.0, **kwargs):
        super().__init__(exporter, **kwargs)
        self.sample_rate = sample_rate

    def emit(self, log_data):
        if random.random() < self.sample_rate:
            super().emit(log_data)


def configure_log_sampling():
    """Attach a sampling export processor to the process-wide LoggerProvider.

    No-op if the app isn't running under `opentelemetry-instrument` (e.g.
    local `manage.py runserver`) — in that case the global provider is the
    SDK's no-op default and has no `add_log_record_processor`.
    """
    provider = get_logger_provider()
    if not hasattr(provider, "add_log_record_processor"):
        return

    sample_rate = float(os.environ.get("OTEL_LOGS_SAMPLE_RATE", "1.0"))
    exporter = OTLPLogExporter()  # reads OTEL_EXPORTER_OTLP_* env vars
    provider.add_log_record_processor(
        SamplingBatchLogRecordProcessor(exporter, sample_rate=sample_rate)
    )
