"""Metrics recorder Protocol + zero-overhead default.

jvspatial does not ship its own metrics backend. We define a small
Protocol that callers can implement (or hand off to a real backend's
adapter) and use a Null default so the cost of "metrics enabled but
no backend" stays at one no-op method call per emission.

Three operations cover everything we currently emit:

* :meth:`MetricsRecorder.record_duration` -- timing histogram /
  summary. Used for ``db.op.duration_seconds``.
* :meth:`MetricsRecorder.increment_counter` -- monotonic counter.
  Used for ``db.op.count`` and cache hit/miss.
* :meth:`MetricsRecorder.record_value` -- single-shot gauge / value
  observation. Used for things like ``db.find.result_count``.

All three accept ``**labels`` so a backend can attach the standard
dimensions: ``backend``, ``op``, ``collection``, ``success``.

OpenTelemetry adapter
---------------------
:mod:`jvspatial.observability.otel` provides an adapter that targets
the OpenTelemetry meter API. Install it via
``pip install jvspatial[otel]`` and use it like::

    from jvspatial.observability.otel import OpenTelemetryMetricsRecorder
    metrics = OpenTelemetryMetricsRecorder()
    db = create_database(..., observe=True, metrics=metrics)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MetricsRecorder(Protocol):
    """Protocol any metrics backend can implement.

    Implementations must NOT raise from any of these methods. A
    metrics backend that's misconfigured or unavailable should swallow
    its own errors -- the calling code path (a database operation)
    must not be affected by metrics emission.
    """

    def record_duration(self, name: str, seconds: float, /, **labels: Any) -> None:
        """Record a duration observation for ``name`` with ``labels``."""
        ...

    def increment_counter(
        self, name: str, /, *, amount: int = 1, **labels: Any
    ) -> None:
        """Increment the named counter by ``amount`` with ``labels``."""
        ...

    def record_value(self, name: str, value: float, /, **labels: Any) -> None:
        """Record a single value observation for ``name`` with ``labels``."""
        ...


class NullMetricsRecorder:
    """Default :class:`MetricsRecorder` that does nothing.

    Used when an :class:`ObservableDatabase` is created without an
    explicit ``metrics=`` argument. Each method is an empty function;
    the per-call cost is the function call itself. We deliberately
    don't make this a class with ``__slots__`` and explicit no-op
    bodies because the simpler form generates equivalent bytecode and
    is easier to read.
    """

    def record_duration(
        self, name: str, seconds: float, /, **labels: Any
    ) -> None:  # noqa: D401
        """No-op."""
        return None

    def increment_counter(
        self, name: str, /, *, amount: int = 1, **labels: Any
    ) -> None:
        """No-op."""
        return None

    def record_value(self, name: str, value: float, /, **labels: Any) -> None:
        """No-op."""
        return None


__all__ = ["MetricsRecorder", "NullMetricsRecorder"]
