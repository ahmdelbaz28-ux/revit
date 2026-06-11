try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory import InMemorySpanExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.propagators.composite import CompositeHTTPPropagator
    from opentelemetry.propagate import set_global_textmap
    _OPENTELEMETRY_AVAILABLE = True
except ImportError:
    trace = None
    TracerProvider = None
    BatchSpanProcessor = None
    InMemorySpanExporter = None
    OTLPSpanExporter = None
    TraceContextTextMapPropagator = None
    CompositeHTTPPropagator = None
    set_global_textmap = None
    _OPENTELEMETRY_AVAILABLE = False

import functools
import typing as t
import logging
from contextvars import ContextVar

_current_span: ContextVar[t.Optional[t.Any]] = ContextVar('current_span', default=None)

if _OPENTELEMETRY_AVAILABLE:
    _propagator = CompositeHTTPPropagator([
        TraceContextTextMapPropagator(),
    ])
else:
    _propagator = None


def setup_tracing(
    service_name: str = 'fireai',
    endpoint: str = 'http://tempo:4318/v1/traces',
    sample_rate: float = 1.0,
) -> TracerProvider | None:
    if not _OPENTELEMETRY_AVAILABLE:
        # Tracing is optional; return None when the library is missing.
        logger = logging.getLogger(__name__)
        logger.warning('OpenTelemetry not available – tracing disabled')
        return None
    provider = TracerProvider()
    exporter = OTLPSpanExporter(endpoint=endpoint)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    if _propagator is not None:
        set_global_textmap(_propagator)
    return provider


def traced(name: t.Optional[str] = None):
    def decorator(fn: t.Callable) -> t.Callable:
        if not _OPENTELEMETRY_AVAILABLE:
            # Tracing disabled – return original function unchanged
            return fn
        tracer = trace.get_tracer(__name__)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            span_name = name or fn.__qualname__
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute('function', fn.__qualname__)
                _current_span.set(span)
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
                    raise
        return wrapper
    return decorator


def get_current_span() -> t.Optional[t.Any]:
    return _current_span.get()


def extract_traceparent(headers: t.Dict[str, str]) -> t.Optional[t.Dict[str, str]]:
    if _propagator is None:
        return None
    ctx = _propagator.extract(headers)
    for carrier in [headers]:
        if 'traceparent' in {k.lower() for k in carrier}:
            return {'traceparent': carrier.get('traceparent') or carrier.get('Traceparent', '')}
    return None


def inject_traceparent(headers: t.Optional[t.Dict[str, str]] = None) -> t.Dict[str, str]:
    if headers is None:
        headers = {}
    if not _OPENTELEMETRY_AVAILABLE or trace is None:
        return headers
    ctx = trace.get_current_span().get_span_context() if trace.get_current_span() else None
    if ctx and ctx.trace_id:
        headers['traceparent'] = f'00-{format(ctx.trace_id, "032x")}-{format(ctx.span_id, "016x")}-01'
    return headers


class TraceContext:
    def __init__(self, app, tracer: t.Optional[t.Any] = None):
        self.app = app
        if not _OPENTELEMETRY_AVAILABLE or trace is None:
            self.tracer = None
        else:
            self.tracer = tracer or trace.get_tracer(__name__)

    async def __call__(self, scope, receive, send):
        # If tracing is disabled, just forward the request.
        if not _OPENTELEMETRY_AVAILABLE or self.tracer is None:
            await self.app(scope, receive, send)
            return

        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        headers = {k.decode(): v.decode() for k, v in scope.get('headers', [])}
        ctx = _propagator.extract(carrier=headers) if _propagator is not None else None

        token = None
        if ctx:
            token = trace.use_span(trace.get_current_span(), end_on_exit=False)

        span_name = f"{scope.get('method', 'GET')} {scope.get('path', '/')}"
        with self.tracer.start_as_current_span(span_name, context=ctx) as span:
            span.set_attribute('http.method', scope.get('method', 'GET'))
            span.set_attribute('http.url', scope.get('path', '/'))
            span.set_attribute('http.host', headers.get('host', ''))

            async def wrapped_send(message):
                if message['type'] == 'http.response.start':
                    span.set_attribute('http.status_code', message.get('status', 0))
                await send(message)

            await self.app(scope, receive, wrapped_send)

        if token:
            trace.detach(token)
