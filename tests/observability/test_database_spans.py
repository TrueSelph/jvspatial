"""Database observations expose timing, never query parameters or errors."""

import pytest


@pytest.mark.asyncio
async def test_observed_database_spans_are_content_free(tmp_path, monkeypatch):
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from jvspatial.db import create_database
    from jvspatial.observability import tracing

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(tracing, "get_tracer", lambda name: provider.get_tracer(name))
    database = create_database("json", base_path=str(tmp_path), observe=True)
    await database.find("node", {"context.title": "private-query-value"})

    async def fail():
        raise ValueError("private-query-value")

    with pytest.raises(ValueError):
        await database._instrument("find", "node", fail)
    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    assert spans[0].attributes["db.success"] is True
    assert spans[1].attributes["error.type"] == "ValueError"
    assert not spans[1].events
    assert "private-query-value" not in str(
        [(s.attributes, s.events, s.status.description) for s in spans]
    )
    provider.shutdown()


@pytest.mark.asyncio
async def test_unconfigured_tracing_keeps_metrics_without_proxy_spans(
    tmp_path, monkeypatch
):
    from opentelemetry import trace

    from jvspatial.db import create_database
    from jvspatial.observability import tracing

    monkeypatch.setattr(trace, "_TRACER_PROVIDER", trace.NoOpTracerProvider())

    def unexpected_tracer(*args, **kwargs):
        raise AssertionError("No SDK should require no proxy span allocation")

    monkeypatch.setattr(tracing, "get_tracer", unexpected_tracer)
    database = create_database("json", base_path=str(tmp_path), observe=True)
    assert await database.find("node", {}) == []


@pytest.mark.asyncio
async def test_walker_run_traces_counts_without_reports_or_exception_content(
    monkeypatch,
):
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from jvspatial.core import Walker

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    walker = Walker()
    assert await walker.run() == []

    async def fail(self):
        raise ValueError("private-report-value")

    monkeypatch.setattr(Walker, "_run_traversal", fail)
    with pytest.raises(ValueError):
        await walker.run()
    spans = exporter.get_finished_spans()
    assert len(spans) == 2
    assert spans[0].attributes["walker.step_count"] == 0
    assert spans[1].attributes["error.type"] == "ValueError"
    assert all(not s.events for s in spans)
    assert "private-report-value" not in str(
        [(s.attributes, s.status.description) for s in spans]
    )
    assert all(
        "walker.id" not in s.attributes and "walker.entry_node" not in s.attributes
        for s in spans
    )
    provider.shutdown()
