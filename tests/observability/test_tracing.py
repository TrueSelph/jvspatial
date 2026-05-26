"""Tests for the OTel tracing helpers.

Verifies:

* The helpers are importable + callable when OTel isn't installed
  (the no-op path) — this is the common case for libraries that ship
  jvspatial as an unconditional dependency.
* Span attributes match OTel semantic conventions when OTel is wired.
* ``inject_traceparent_into`` returns a dict whether or not OTel is
  present.

Exercising the "OTel installed and SDK configured" path requires the
opentelemetry-sdk package; we add an integration-style test that runs
only when those modules import cleanly.
"""

from __future__ import annotations

import pytest

from jvspatial.observability.tracing import (
    db_span,
    get_tracer,
    http_span,
    inject_traceparent_into,
    is_tracing_available,
    walker_span,
)


class TestNoopPath:
    """Behavior when the OTel API isn't installed (or no SDK is wired)."""

    def test_get_tracer_returns_object(self) -> None:
        # Whatever the deployment posture, get_tracer() must always
        # return something usable.
        assert get_tracer("test") is not None

    def test_db_span_is_a_context_manager(self) -> None:
        with db_span("find", collection="x", backend="postgresql") as span:
            assert span is not None
            span.set_attribute("custom.attr", 1)

    def test_walker_span_is_a_context_manager(self) -> None:
        with walker_span("PageRank", walker_id="w.1") as span:
            assert span is not None

    def test_http_span_is_a_context_manager(self) -> None:
        with http_span("GET", "/users/{id}") as span:
            assert span is not None

    def test_inject_traceparent_returns_dict(self) -> None:
        out = inject_traceparent_into({"X-Custom": "1"})
        assert isinstance(out, dict)
        assert out["X-Custom"] == "1"

    def test_db_span_records_exceptions_without_raising_in_handler(self) -> None:
        with pytest.raises(ValueError):
            with db_span("save", collection="user", backend="sqlite"):
                raise ValueError("boom")


# Only run the SDK-required suite when both the API + SDK + in-memory
# exporter are available.
sdk = pytest.importorskip("opentelemetry.sdk.trace", reason="needs OTel SDK")


@pytest.fixture(scope="module")
def _otel_provider():
    """Install one TracerProvider for the whole module.

    OTel only allows a single provider per process — re-setting it is a
    silent no-op + warning. So we install once and reuse, clearing the
    in-memory exporter between tests for isolation.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    yield exporter


class TestOtelWiring:
    """Behavior when OTel is wired with the in-memory test exporter."""

    @pytest.fixture(autouse=True)
    def _exporter(self, _otel_provider):
        self.exporter = _otel_provider
        self.exporter.clear()
        yield

    def test_tracing_is_available(self) -> None:
        assert is_tracing_available() is True

    def test_db_span_sets_semantic_attributes(self) -> None:
        with db_span("find", collection="user", backend="postgresql") as span:
            span.set_attribute("db.result_count", 7)
        spans = self.exporter.get_finished_spans()
        assert len(spans) == 1
        attrs = dict(spans[0].attributes)
        assert attrs["db.system"] == "postgresql"
        assert attrs["db.operation"] == "find"
        assert attrs["db.collection.name"] == "user"
        assert attrs["db.result_count"] == 7

    def test_walker_span_sets_semantic_attributes(self) -> None:
        with walker_span("PageRank", walker_id="w.1", entry_node_id="n.A") as span:
            span.set_attribute("walker.step_count", 42)
        spans = self.exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs["walker.class"] == "PageRank"
        assert attrs["walker.id"] == "w.1"
        assert attrs["walker.entry_node"] == "n.A"
        assert attrs["walker.step_count"] == 42

    def test_http_span_sets_semantic_attributes(self) -> None:
        with http_span("POST", "/users") as span:
            span.set_attribute("http.status_code", 201)
        spans = self.exporter.get_finished_spans()
        attrs = dict(spans[0].attributes)
        assert attrs["http.method"] == "POST"
        assert attrs["http.route"] == "/users"
        assert attrs["http.status_code"] == 201

    def test_exception_marks_span_error(self) -> None:
        with pytest.raises(RuntimeError):
            with db_span("save", collection="user", backend="postgresql"):
                raise RuntimeError("write failed")
        span = self.exporter.get_finished_spans()[0]
        # ERROR is StatusCode.ERROR == 2 in OTel.
        assert span.status.status_code.name == "ERROR"

    def test_inject_traceparent_adds_header(self) -> None:
        # Need an active span for there to be a context to inject.
        with http_span("GET", "/x"):
            headers = inject_traceparent_into({})
            assert "traceparent" in headers
