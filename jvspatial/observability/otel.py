"""OpenTelemetry adapter for :class:`MetricsRecorder`.

This module is **only** importable when ``opentelemetry-api`` is
available. Install it via the ``otel`` extra::

    pip install jvspatial[otel]

The adapter targets the OpenTelemetry meter API. If your application
hasn't configured an SDK + exporter, the meter calls become no-ops by
design -- so you can use this adapter unconditionally and only pay
for emission when something is actually consuming it.

Example::

    from jvspatial.observability.otel import OpenTelemetryMetricsRecorder
    from jvspatial.db import create_database

    metrics = OpenTelemetryMetricsRecorder()
    db = create_database(
        "sqlite", db_path="./app.db",
        observe=True, metrics=metrics,
    )

Why we implement this on top of the meter API and not the SDK
-------------------------------------------------------------
The application owns the SDK (which exporters, which resource
attributes, etc.). This adapter just reaches for whatever ``MeterProvider``
the application has installed. That's the OpenTelemetry-recommended
shape for library code.

Instrument cache
----------------
Histograms and counters are cached per-name so repeated emissions
don't recreate the instrument on every call.
"""

from __future__ import annotations

import contextlib
from threading import Lock
from typing import Any, Dict, Optional

try:
    from opentelemetry import metrics as otel_metrics  # type: ignore
except ImportError as exc:  # pragma: no cover - exercised only without OTel
    raise ImportError(
        "OpenTelemetryMetricsRecorder requires the 'opentelemetry-api' "
        "package. Install it with: pip install jvspatial[otel]"
    ) from exc


class OpenTelemetryMetricsRecorder:
    """:class:`MetricsRecorder` backed by the OpenTelemetry meter API.

    Args:
        meter_name: Name passed to :func:`opentelemetry.metrics.get_meter`.
            Defaults to ``"jvspatial"``.
        meter_version: Optional version string for the meter.
        meter_provider: Optional explicit
            :class:`opentelemetry.metrics.MeterProvider`. Defaults to
            the global one (which the application configures via the
            SDK).
    """

    def __init__(
        self,
        meter_name: str = "jvspatial",
        meter_version: Optional[str] = None,
        meter_provider: Any = None,
    ) -> None:
        if meter_provider is None:
            self._meter = otel_metrics.get_meter(meter_name, meter_version)
        else:
            self._meter = meter_provider.get_meter(meter_name, meter_version)
        # Per-instrument caches so we don't recreate on every call.
        self._histograms: Dict[str, Any] = {}
        self._counters: Dict[str, Any] = {}
        self._gauges: Dict[str, Any] = {}
        self._lock = Lock()

    def _get_histogram(self, name: str) -> Any:
        h = self._histograms.get(name)
        if h is not None:
            return h
        with self._lock:
            h = self._histograms.get(name)
            if h is None:
                h = self._meter.create_histogram(
                    name,
                    description="jvspatial duration histogram",
                    unit="s",
                )
                self._histograms[name] = h
        return h

    def _get_counter(self, name: str) -> Any:
        c = self._counters.get(name)
        if c is not None:
            return c
        with self._lock:
            c = self._counters.get(name)
            if c is None:
                c = self._meter.create_counter(
                    name,
                    description="jvspatial counter",
                )
                self._counters[name] = c
        return c

    def _get_gauge_histogram(self, name: str) -> Any:
        """Use a histogram for value observations.

        OTel doesn't have a sync gauge that takes a single observation,
        so a histogram is the right call for "record this value once."
        """
        return self._get_histogram(name + ".values")

    @staticmethod
    def _coerce_attrs(labels: Dict[str, Any]) -> Dict[str, Any]:
        """Coerce label values to OTel-acceptable primitive types.

        We pass strings through unchanged. Booleans become ``"true"``/
        ``"false"`` strings (OTel does accept booleans, but emitter
        backends often render them inconsistently across exporters;
        strings are safer).
        """
        out: Dict[str, Any] = {}
        for k, v in labels.items():
            if isinstance(v, bool):
                out[k] = "true" if v else "false"
            elif isinstance(v, (str, int, float)):
                out[k] = v
            elif v is None:
                continue
            else:
                out[k] = str(v)
        return out

    def record_duration(self, name: str, seconds: float, /, **labels: Any) -> None:
        """Record a duration sample on the OTel histogram for ``name``."""
        # Per the protocol contract, never raise from a metrics call.
        with contextlib.suppress(Exception):
            self._get_histogram(name).record(
                seconds, attributes=self._coerce_attrs(labels)
            )

    def increment_counter(
        self, name: str, /, *, amount: int = 1, **labels: Any
    ) -> None:
        """Increment the OTel counter for ``name`` by ``amount``."""
        with contextlib.suppress(Exception):
            self._get_counter(name).add(amount, attributes=self._coerce_attrs(labels))

    def record_value(self, name: str, value: float, /, **labels: Any) -> None:
        """Record a single-shot value sample for ``name``."""
        with contextlib.suppress(Exception):
            self._get_gauge_histogram(name).record(
                float(value), attributes=self._coerce_attrs(labels)
            )


__all__ = ["OpenTelemetryMetricsRecorder"]
