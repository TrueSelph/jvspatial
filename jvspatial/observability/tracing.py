"""OpenTelemetry tracing helpers for jvspatial.

The library already ships :class:`MetricsRecorder` (and its OTel adapter)
for per-op metrics. Tracing is the other half: it lets you follow a
single request through FastAPI → AuthService → Walker → Database in a
distributed trace tool (Jaeger, Tempo, Honeycomb, Datadog, etc.).

This module exposes a thin tracer helper plus context managers for the
boundaries jvspatial cares about. Like the metrics adapter, the
application owns the SDK (which exporter, which resource attributes);
this module only reaches for whatever ``TracerProvider`` is installed.
If no SDK is configured the spans are no-ops, so it's safe to wire the
helpers unconditionally.

Install via the ``otel`` extra::

    pip install jvspatial[otel]

Then wire the SDK in your application bootstrap::

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )

    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

After that, jvspatial's internal ``with tracer.start_as_current_span(...)``
calls emit spans to your configured exporter.

Span surface
------------
:func:`db_span` wraps a database operation (one span per call).
:func:`walker_span` wraps ``Walker.run`` so traversal cost is visible.
:func:`http_span` is for the FastAPI middleware (in
``jvspatial.api.components.middleware``). All three set semantic
attributes following the
[OpenTelemetry conventions](https://opentelemetry.io/docs/specs/semconv/).

When the optional dep is missing the helpers return a no-op context
manager, keeping the library importable with zero observability surface.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

# ``opentelemetry-api`` is the only optional dep — install via
# ``jvspatial[otel]``. The SDK is owned by the application.
try:
    from opentelemetry import trace as _otel_trace  # type: ignore
    from opentelemetry.trace import (  # type: ignore
        SpanKind,
        Status,
        StatusCode,
    )

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False

    class SpanKind:  # type: ignore[no-redef]
        INTERNAL = "internal"
        SERVER = "server"
        CLIENT = "client"

    class StatusCode:  # type: ignore[no-redef]
        UNSET = "unset"
        OK = "ok"
        ERROR = "error"

    class Status:  # type: ignore[no-redef]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass


# ---- core tracer access ----------------------------------------------------


def is_tracing_available() -> bool:
    """Return True when the OTel API is importable. Safe to call always."""
    return _OTEL_AVAILABLE


def get_tracer(name: str = "jvspatial") -> Any:
    """Return an OTel ``Tracer`` for emitting spans.

    When OTel isn't installed, returns a small stub whose context
    manager methods are no-ops — callers can write the same code path
    regardless of deployment configuration.

    Args:
        name: Tracer name. Defaults to ``"jvspatial"``; library code
            should pass a more specific name (e.g. ``"jvspatial.db"``)
            so traces can be filtered by source.
    """
    if not _OTEL_AVAILABLE:
        return _NoopTracer()
    return _otel_trace.get_tracer(name)  # type: ignore[no-any-return]


class _NoopSpan:
    """No-op span returned when OTel isn't installed.

    Mirrors enough of the Tracer.Span protocol that calling code never
    has to branch on ``is_tracing_available()`` — set attributes, mark
    errors, even check ``is_recording()`` and everything quietly does
    nothing.
    """

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def set_attribute(self, _key: str, _value: Any) -> None:
        return None

    def set_status(self, _status: Any, _description: Optional[str] = None) -> None:
        return None

    def record_exception(self, _exc: BaseException, **_kwargs: Any) -> None:
        return None

    def is_recording(self) -> bool:
        return False


class _NoopTracer:
    """No-op tracer for the OTel-not-installed path."""

    def start_as_current_span(self, _name: str, **_kwargs: Any) -> _NoopSpan:
        return _NoopSpan()

    def start_span(self, _name: str, **_kwargs: Any) -> _NoopSpan:
        return _NoopSpan()


# ---- domain-specific span helpers ------------------------------------------


@contextlib.contextmanager
def db_span(
    op: str,
    *,
    collection: Optional[str] = None,
    backend: Optional[str] = None,
    tracer_name: str = "jvspatial.db",
) -> Iterator[Any]:
    """Wrap a database operation in a span.

    Sets OTel semantic conventions for DB calls so trace UIs render
    these correctly without further configuration:

    * ``db.system`` = ``backend`` (``"postgresql"``, ``"mongodb"``, etc.)
    * ``db.operation`` = ``op`` (``"save"``, ``"find"``, ``"delete"``…)
    * ``db.collection.name`` = ``collection``

    Usage in the adapter::

        with db_span("find", collection="user", backend="postgresql") as span:
            rows = await self._do_find(...)
            span.set_attribute("db.result_count", len(rows))

    Args:
        op: Database operation name.
        collection: Collection / table touched. Optional — omit for ops
            that span multiple collections (e.g. bootstrap).
        backend: Backend identifier. Recommended values use the OTel
            ``db.system`` convention (``"postgresql"``, ``"mongodb"``,
            ``"sqlite"``, ``"dynamodb"``, ``"jsondb"``).
        tracer_name: Override the tracer source name. Default
            ``"jvspatial.db"``.
    """
    tracer = get_tracer(tracer_name)
    span_name = f"db.{op}"
    if collection:
        span_name = f"db.{op} {collection}"
    with tracer.start_as_current_span(
        span_name,
        kind=SpanKind.CLIENT if _OTEL_AVAILABLE else None,
    ) as span:
        if backend:
            span.set_attribute("db.system", backend)
        span.set_attribute("db.operation", op)
        if collection:
            span.set_attribute("db.collection.name", collection)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(
                Status(StatusCode.ERROR, str(exc)) if _OTEL_AVAILABLE else None
            )
            raise


@contextlib.contextmanager
def walker_span(
    walker_class: str,
    *,
    walker_id: Optional[str] = None,
    entry_node_id: Optional[str] = None,
    tracer_name: str = "jvspatial.walker",
) -> Iterator[Any]:
    """Wrap a ``Walker.run`` invocation in a span.

    Sets attributes that make graph traversals legible in trace UIs:

    * ``walker.class`` = ``walker_class``
    * ``walker.id`` = ``walker_id`` (when known)
    * ``walker.entry_node`` = entry node id (when known)
    * Step count + termination reason can be set by the caller via
      ``span.set_attribute("walker.step_count", ...)`` on exit.

    Args:
        walker_class: Class name of the walker (e.g. ``"PageRankWalker"``).
        walker_id: Stable id of this walker invocation.
        entry_node_id: Node id the walker spawned from.
        tracer_name: Override the tracer source name.
    """
    tracer = get_tracer(tracer_name)
    span_name = f"walker.run {walker_class}"
    with tracer.start_as_current_span(
        span_name,
        kind=SpanKind.INTERNAL if _OTEL_AVAILABLE else None,
    ) as span:
        span.set_attribute("walker.class", walker_class)
        if walker_id:
            span.set_attribute("walker.id", walker_id)
        if entry_node_id:
            span.set_attribute("walker.entry_node", entry_node_id)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(
                Status(StatusCode.ERROR, str(exc)) if _OTEL_AVAILABLE else None
            )
            raise


@contextlib.contextmanager
def http_span(
    method: str,
    path: str,
    *,
    tracer_name: str = "jvspatial.http",
) -> Iterator[Any]:
    """Wrap an inbound HTTP request in a SERVER span.

    Intended for the FastAPI middleware adapter (the actual middleware
    lives in ``jvspatial.api.components.middleware``). Sets standard
    OTel ``http.*`` attributes; the caller fills in status code +
    response size on exit.

    Args:
        method: HTTP method (e.g. ``"GET"``).
        path: Route template or path (e.g. ``"/users/{id}"``).
        tracer_name: Override the tracer source name.
    """
    tracer = get_tracer(tracer_name)
    span_name = f"http.{method.lower()} {path}"
    with tracer.start_as_current_span(
        span_name,
        kind=SpanKind.SERVER if _OTEL_AVAILABLE else None,
    ) as span:
        span.set_attribute("http.method", method)
        span.set_attribute("http.route", path)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(
                Status(StatusCode.ERROR, str(exc)) if _OTEL_AVAILABLE else None
            )
            raise


def inject_traceparent_into(headers: Optional[dict] = None) -> dict:
    """Inject the active W3C ``traceparent`` header into ``headers``.

    Used by outbound calls (webhooks, deferred-task payloads) so the
    receiving worker can continue the trace.

    Returns the modified headers dict; pass an empty dict to get back
    a fresh one. No-op when OTel isn't installed.
    """
    out = dict(headers or {})
    if not _OTEL_AVAILABLE:
        return out
    try:
        from opentelemetry.propagate import inject  # type: ignore

        inject(out)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("traceparent injection failed: %s", exc)
    return out


__all__ = [
    "db_span",
    "walker_span",
    "http_span",
    "get_tracer",
    "is_tracing_available",
    "inject_traceparent_into",
]
