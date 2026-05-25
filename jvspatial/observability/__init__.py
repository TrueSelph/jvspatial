"""Observability primitives.

Two surfaces live here:

* :class:`MetricsRecorder` -- a tiny Protocol that any metrics backend
  (StatsD, Prometheus, OpenTelemetry, your own thing) can implement.
  The default implementation, :class:`NullMetricsRecorder`, has zero
  overhead beyond a method call.
* :class:`ObservableDatabase` -- a :class:`Database` wrapper (see
  ``jvspatial.db._observable``) that emits a structured log line and
  one metric per database operation. Opt-in via
  ``create_database(..., observe=True)``.

Both surfaces are public. See ``docs/md/observability.md`` for the
contract and ``docs/md/stability.md`` for the stability tier.
"""

from contextvars import ContextVar

from jvspatial.observability.metrics import (
    MetricsRecorder,
    NullMetricsRecorder,
)

# Per-request (or per-logical execution flow) database operation counter.
# ObservableDatabase increments this on every wrapped operation so callers
# can cheaply surface round-trip count in headers/logs.
db_op_counter: ContextVar[int] = ContextVar("jvspatial_db_op_counter", default=0)

__all__ = [
    "MetricsRecorder",
    "NullMetricsRecorder",
    "db_op_counter",
]
