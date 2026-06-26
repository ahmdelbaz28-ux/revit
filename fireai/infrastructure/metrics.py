import functools
import time
from typing import Callable

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

METRIC_ENGINE_RUNS = Counter(
    'fireai_engine_runs_total', 'Total engine runs', ['engine', 'status']
)
METRIC_COMPUTATION_TIME = Histogram(
    'fireai_computation_seconds', 'Computation time', ['engine'],
    buckets=[0.01, 0.1, 0.5, 1, 5, 10, 30, 60]
)
METRIC_DETECTORS_PLACED = Gauge(
    'fireai_detectors_placed', 'Detectors placed per room', ['room_type']
)
METRIC_COVERAGE_PCT = Gauge(
    'fireai_coverage_percent', 'Coverage percentage', ['room_id', 'status']
)
METRIC_ACTIVE_WORKFLOWS = Gauge(
    'fireai_active_workflows', 'Active workflow count'
)
METRIC_API_LATENCY = Histogram(
    'fireai_api_latency_seconds', 'API latency', ['endpoint', 'method']
)
METRIC_ERRORS = Counter(
    'fireai_errors_total', 'Error count', ['component', 'type']
)
METRIC_MEMORY_BYTES = Gauge(
    'fireai_memory_bytes', 'Process memory', ['component']
)
METRIC_QUEUE_DEPTH = Gauge(
    'fireai_queue_depth', 'Work queue depth', ['queue']
)


def track_engine_run(engine: str):
    """Decorator factory that records engine run counts, errors, and computation time."""
    def decorator(fn: Callable):
        """Wrap *fn* with Prometheus metric instrumentation."""
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            """Execute the wrapped function, recording success/failure and latency metrics."""
            start = time.monotonic()
            try:
                result = fn(*args, **kwargs)
                METRIC_ENGINE_RUNS.labels(engine=engine, status='success').inc()
                return result
            except Exception as exc:
                METRIC_ENGINE_RUNS.labels(engine=engine, status='error').inc()
                METRIC_ERRORS.labels(component=engine, type=type(exc).__name__).inc()
                raise
            finally:
                elapsed = time.monotonic() - start
                METRIC_COMPUTATION_TIME.labels(engine=engine).observe(elapsed)
        return wrapper
    return decorator


def metrics_endpoint():
    """Return a Prometheus-format metrics scrape response."""
    data = generate_latest()
    return data, 200, {'Content-Type': CONTENT_TYPE_LATEST}
