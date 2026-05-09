"""Tests for the optional OpenTelemetry adapter.

Skipped when ``opentelemetry-api`` is not installed; meaningful only
under the ``[otel]`` extra.
"""

import pytest

otel_metrics = pytest.importorskip("opentelemetry.metrics")
from jvspatial.observability.otel import OpenTelemetryMetricsRecorder  # noqa: E402


class TestOpenTelemetryAdapter:
    def test_constructible_without_explicit_provider(self):
        rec = OpenTelemetryMetricsRecorder()
        # The default global provider returns a no-op meter when no SDK
        # is installed, which is exactly the behavior we want.
        assert rec is not None

    def test_record_methods_do_not_raise_under_default_provider(self):
        rec = OpenTelemetryMetricsRecorder()
        # All three methods must be safe to call repeatedly with no
        # SDK configured.
        rec.record_duration(
            "jvspatial.test.duration", 0.001, op="get", collection="node"
        )
        rec.increment_counter("jvspatial.test.counter", op="save", collection="node")
        rec.record_value("jvspatial.test.value", 42.0, op="find", collection="node")

    def test_repeated_calls_share_instruments(self):
        rec = OpenTelemetryMetricsRecorder()
        rec.record_duration("d", 0.001)
        rec.record_duration("d", 0.002)
        # Internal cache should have exactly one histogram entry.
        assert "d" in rec._histograms
        assert len(rec._histograms) == 1

    def test_attributes_coerced_for_emitter(self):
        rec = OpenTelemetryMetricsRecorder()
        # Booleans must coerce to strings rather than raise. We can't
        # easily inspect the emitted record without the SDK; instead
        # we just check that the call completes.
        rec.increment_counter(
            "jvspatial.test.bool", success=True, op="get", collection="x"
        )

    def test_metrics_failure_swallowed(self):
        """Adapter must not raise on emission, even if the underlying
        instrument call somehow fails."""
        rec = OpenTelemetryMetricsRecorder()

        # Replace one instrument with a misbehaving one.
        class _Boom:
            def record(self, *a, **k):
                raise RuntimeError("emitter broken")

        rec._histograms["d"] = _Boom()
        rec.record_duration("d", 0.001)  # must not raise
