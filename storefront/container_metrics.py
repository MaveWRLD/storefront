"""Container-scoped resource metrics read from cgroup v2.

opentelemetry-instrumentation-system-metrics is disabled on purpose
(Procfile's OTEL_PYTHON_DISABLED_INSTRUMENTATIONS): it reads /proc via
psutil, and inside a Railway container /proc is the host's, so it
reported the whole machine rather than this container's slice. The
cgroup files below are the only in-container source that reflects the
actual limit and the actual usage.

Everything here is an observable gauge — the callbacks run once per
export interval (OTEL_METRIC_EXPORT_INTERVAL, 5 min in prod) and read
a handful of small sysfs files, so the cost is negligible. Total series
added is ~13, against Grafana Cloud's 10k active-series cap.

Emitted by exactly one gunicorn worker; see core/apps.py for why.
"""
from pathlib import Path

from opentelemetry import metrics

CGROUP = Path('/sys/fs/cgroup')


def _read(name):
    try:
        return (CGROUP / name).read_text().strip()
    except OSError:
        return None


def _read_int(name):
    raw = _read(name)
    if raw is None or raw == 'max':
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _read_kv(name):
    """Parse the 'key value' per-line files: memory.stat, cpu.stat, memory.events."""
    raw = _read(name)
    if raw is None:
        return {}
    out = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip('-').isdigit():
            out[parts[0]] = int(parts[1])
    return out


def _cpu_limit_cores():
    """cpu.max is '<quota> <period>' in microseconds, or 'max <period>' if uncapped."""
    raw = _read('cpu.max')
    if not raw:
        return None
    quota, _, period = raw.partition(' ')
    if quota == 'max':
        return None
    try:
        return int(quota) / int(period or 100000)
    except ValueError:
        return None


def available():
    """cgroup v2 present? v1 has a different layout; Railway is v2."""
    return (CGROUP / 'cpu.stat').exists()


def _observe_memory(_options):
    out = []
    used = _read_int('memory.current')
    stat = _read_kv('memory.stat')
    if used is not None:
        # memory.current counts reclaimable page cache too. The anon figure
        # is what actually gets you OOM-killed, so report both — a container
        # sitting at 95% of limit on page cache is fine, on anon it is not.
        out.append(metrics.Observation(used, {'state': 'total'}))
        if 'file' in stat:
            out.append(metrics.Observation(used - stat['file'], {'state': 'anon'}))
    limit = _read_int('memory.max')
    if limit is not None:
        out.append(metrics.Observation(limit, {'state': 'limit'}))
    # High-water mark since boot — this is the right-sizing number, and it
    # survives spikes shorter than the 5 min export interval.
    peak = _read_int('memory.peak')
    if peak is not None:
        out.append(metrics.Observation(peak, {'state': 'peak'}))
    return out


def _observe_cpu(_options):
    out = []
    stat = _read_kv('cpu.stat')
    if 'usage_usec' in stat:
        out.append(metrics.Observation(
            stat['usage_usec'] / 1e6, {'state': 'used_seconds'}))
    # Non-zero throttling means the CPU quota is the bottleneck, not the code.
    if 'throttled_usec' in stat:
        out.append(metrics.Observation(
            stat['throttled_usec'] / 1e6, {'state': 'throttled_seconds'}))
    if 'nr_throttled' in stat:
        out.append(metrics.Observation(
            stat['nr_throttled'], {'state': 'throttled_periods'}))
    cores = _cpu_limit_cores()
    if cores is not None:
        out.append(metrics.Observation(cores, {'state': 'limit_cores'}))
    return out


def _observe_memory_events(_options):
    events = _read_kv('memory.events')
    return [
        metrics.Observation(events.get(key, 0), {'event': key})
        for key in ('oom', 'oom_kill', 'high')
        if key in events
    ]


def _observe_pids(_options):
    out = []
    current = _read_int('pids.current')
    if current is not None:
        out.append(metrics.Observation(current, {'state': 'current'}))
    limit = _read_int('pids.max')
    if limit is not None:
        out.append(metrics.Observation(limit, {'state': 'limit'}))
    return out


def register():
    meter = metrics.get_meter('storefront.container')
    meter.create_observable_gauge(
        'container.memory.bytes',
        callbacks=[_observe_memory],
        unit='By',
        description='cgroup v2 memory usage, limit and peak',
    )
    meter.create_observable_gauge(
        'container.cpu',
        callbacks=[_observe_cpu],
        unit='1',
        description='cgroup v2 cumulative CPU usage, throttling and quota',
    )
    meter.create_observable_gauge(
        'container.memory.events',
        callbacks=[_observe_memory_events],
        unit='1',
        description='cgroup v2 memory pressure and OOM-kill counters',
    )
    meter.create_observable_gauge(
        'container.pids',
        callbacks=[_observe_pids],
        unit='1',
        description='cgroup v2 process/thread count against limit',
    )
