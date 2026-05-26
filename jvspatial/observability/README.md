# jvspatial/observability

Metrics protocol, default no-op recorder, OpenTelemetry adapter.

> **Read first**: [SPEC §14](../../SPEC.md), [docs/md/observability.md](../../docs/md/observability.md)

---

## Purpose

`observability/` defines a tiny protocol (`MetricsRecorder`) that any metrics backend can implement. The library wires `ObservableDatabase` (internal, in `jvspatial/db/_observable.py`) to emit a structured log line and one metric per DB operation, with WARNING-level elevation past a configurable slow-query threshold.

## Layout

```
observability/
├── metrics.py     # MetricsRecorder Protocol + NullMetricsRecorder
└── otel.py        # OpenTelemetryMetricsRecorder (optional, [otel] extra)
```

## Public API (from `jvspatial.observability`)

| Name | What it does |
|---|---|
| `MetricsRecorder` | Protocol implemented by metrics backends |
| `NullMetricsRecorder` | Default no-op |

From `jvspatial.observability.otel` (requires `pip install jvspatial[otel]`):

| Name | What it does |
|---|---|
| `OpenTelemetryMetricsRecorder` | OTEL implementation of `MetricsRecorder` |

## Invariants

- **The structured log field set from `ObservableDatabase` is public.** Schema: `backend`, `op`, `collection`, `duration_ms`, `success`, `result_count`. Breaking changes require a deprecation cycle. (See [docs/md/stability.md](../../docs/md/stability.md).)
- **`NullMetricsRecorder` is zero-overhead.** Calls dispatch to no-op methods; do not add allocations or branching here.
- **Slow-query threshold elevates the log to WARNING.** Configurable per database via `create_database(..., slow_query_ms=N)`.
- **Four metric names are emitted per DB op**: `jvspatial.db.op.duration_seconds`, `jvspatial.db.op.count`, `jvspatial.db.op.slow_count`, `jvspatial.db.op.result_count`.

## Modification patterns

- **Adding a metrics backend**: implement the `MetricsRecorder` protocol. No subclassing required; structural typing applies. Pass via `create_database(..., metrics=YourRecorder())`.
- **Adding a new metric**: extend the protocol with a new method, default-implement on `NullMetricsRecorder` so existing recorders do not break. Document in `docs/md/observability.md` and add to the stability tier table.
- **Changing emitted log fields**: requires a deprecation cycle. Add the new field alongside the old, deprecate the old, remove after one minor cycle.

## Related docs

- [docs/md/observability.md](../../docs/md/observability.md)
- [docs/md/benchmarks.md](../../docs/md/benchmarks.md)
- [docs/md/stability.md](../../docs/md/stability.md)

## Stability

`MetricsRecorder`, `NullMetricsRecorder`, and the `ObservableDatabase` log field set are all stable. `OpenTelemetryMetricsRecorder` is stable when the `[otel]` extra is installed.
