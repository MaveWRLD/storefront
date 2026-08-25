"""Manual OTel instrumentation for what `opentelemetry-instrument`'s
zero-code auto-instrumentation can't express.

`system_metrics` is disabled instrumentation-wide via
OTEL_PYTHON_DISABLED_INSTRUMENTATIONS (see .env) because it bundles host
metrics (system.*, generic process.*) with Python runtime metrics
(process.runtime.*, cpython.gc.*) in one instrumentor — no env-var knob
splits them. We only want the host ones gone, so re-enable the instrumentor
here with a config that keeps just the runtime/gc metrics.
"""

from opentelemetry.instrumentation.system_metrics import (
    SystemMetricsInstrumentor,
)

# Keys are the instrumentor's own metric names (see its _DEFAULT_CONFIG) —
# only the ones scoped to *this process's* Python runtime, not the host.
RUNTIME_METRICS_CONFIG = {
    "process.runtime.memory": None,
    "process.runtime.cpu.time": None,
    "process.runtime.cpu.utilization": None,
    "process.runtime.gc_count": None,
    "process.runtime.thread_count": None,
    "process.runtime.context_switches": None,
    "cpython.gc.collections": None,
    "cpython.gc.collected_objects": None,
    "cpython.gc.uncollectable_objects": None,
}


def instrument_runtime_metrics() -> None:
    """Emit process.runtime.*/cpython.gc.* only — no host system.* metrics.

    Safe to call more than once: BaseInstrumentor tracks its own
    already-instrumented state and no-ops on repeat calls.
    """
    SystemMetricsInstrumentor(config=RUNTIME_METRICS_CONFIG).instrument()
