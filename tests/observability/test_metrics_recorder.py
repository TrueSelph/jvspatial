"""Tests for the MetricsRecorder Protocol and Null default."""

from typing import Any, List, Tuple

import pytest

from jvspatial.observability.metrics import (
    MetricsRecorder,
    NullMetricsRecorder,
)


class _CapturingRecorder:
    """Minimal MetricsRecorder implementation that captures calls."""

    def __init__(self) -> None:
        self.durations: List[Tuple[str, float, dict]] = []
        self.counters: List[Tuple[str, int, dict]] = []
        self.values: List[Tuple[str, float, dict]] = []

    def record_duration(self, name: str, seconds: float, /, **labels: Any) -> None:
        self.durations.append((name, seconds, dict(labels)))

    def increment_counter(
        self, name: str, /, *, amount: int = 1, **labels: Any
    ) -> None:
        self.counters.append((name, amount, dict(labels)))

    def record_value(self, name: str, value: float, /, **labels: Any) -> None:
        self.values.append((name, value, dict(labels)))


class TestProtocolStructuralCheck:
    def test_capturing_recorder_satisfies_protocol(self):
        # runtime_checkable Protocol -> isinstance() works.
        assert isinstance(_CapturingRecorder(), MetricsRecorder)

    def test_null_recorder_satisfies_protocol(self):
        assert isinstance(NullMetricsRecorder(), MetricsRecorder)


class TestNullRecorder:
    def test_null_record_duration_returns_none(self):
        assert NullMetricsRecorder().record_duration("x", 0.1) is None

    def test_null_increment_counter_returns_none(self):
        assert NullMetricsRecorder().increment_counter("x") is None

    def test_null_record_value_returns_none(self):
        assert NullMetricsRecorder().record_value("x", 42.0) is None

    def test_null_accepts_labels(self):
        # Just exercising the keyword path so a regression that
        # accidentally requires positional args would fail.
        NullMetricsRecorder().record_duration("x", 0.1, op="get", collection="node")
