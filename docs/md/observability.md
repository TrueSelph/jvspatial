# Observability

jvspatial ships two opt-in observability layers that wrap any
:class:`Database`. Both are off by default — neither costs anything
unless you turn it on.

## Structured database logging

Wrapping a database with `observe=True` emits a single structured log
line per operation with this fixed schema:

| Field           | Type     | Notes                                            |
| --------------- | -------- | ------------------------------------------------ |
| `backend`       | string   | The underlying adapter class (e.g. `JsonDB`)     |
| `op`            | string   | One of `save`, `get`, `delete`, `find`, `count`, `find_one`, `find_one_and_update`, `find_one_and_delete` |
| `collection`    | string   | Collection name passed to the call               |
| `duration_ms`   | float    | Wall time of the underlying call, milliseconds   |
| `success`       | bool     | False if the call raised                         |
| `result_count`  | int?     | Where applicable: 0/1 for single-doc ops, list length for `find`, the count for `count` |

The line is emitted at INFO level, or **WARNING** when `duration_ms`
exceeds the configurable `slow_query_ms` threshold (default 100 ms).
The standard fields land in `record.__dict__` via the logging
`extra=` channel, so structured-log handlers (json formatters,
`structlog`, OpenTelemetry log exporters) pick them up directly.

```python
from jvspatial.db import create_database

db = create_database(
    "sqlite",
    db_path="./app.db",
    observe=True,
    slow_query_ms=50.0,   # tighten or loosen as needed
)

# Every operation now logs a structured line.
await db.get("node", "abc")
# 2026-05-08T... INFO jvspatial.db.observable
#   db.get on 'node' took 1.42ms
#   {backend: JsonDB, op: get, collection: node, success: true,
#    duration_ms: 1.42, result_count: 1}
```

The logger name is `jvspatial.db.observable`. Add a handler / level
filter against that name when you want to direct DB telemetry to a
specific sink.

## Metrics

Pass a `MetricsRecorder` implementation to record durations, counts,
and result-count observations to your metrics backend.

The Protocol is intentionally small (three methods) so any backend
can be wired up in a few lines:

```python
from typing import Any
from jvspatial.observability.metrics import MetricsRecorder

class MyStatsdRecorder:
    def record_duration(self, name: str, seconds: float, /, **labels: Any):
        ...
    def increment_counter(self, name: str, /, *, amount: int = 1, **labels: Any):
        ...
    def record_value(self, name: str, value: float, /, **labels: Any):
        ...

# Verify it satisfies the Protocol (it's @runtime_checkable):
assert isinstance(MyStatsdRecorder(), MetricsRecorder)
```

### Emitted metric names

| Metric                                   | Type      | When                                  |
| ---------------------------------------- | --------- | ------------------------------------- |
| `jvspatial.db.op.duration_seconds`       | duration  | Every operation                       |
| `jvspatial.db.op.count`                  | counter   | Every operation (success or failure)  |
| `jvspatial.db.op.slow_count`             | counter   | When `duration_ms >= slow_query_ms`   |
| `jvspatial.db.op.result_count`           | value     | Where applicable (find/count/etc.)    |

All four carry the same standard labels as the log line:
`backend`, `op`, `collection`, `success`.

### Per-request operation counter

`jvspatial.observability.db_op_counter` is a `ContextVar[int]` incremented by
`ObservableDatabase` on every instrumented call. Use it in tests or middleware
to assert logical DB operation counts:

```python
from jvspatial.observability import db_op_counter
from jvspatial.db import create_database

db = create_database("json", base_path="./data", observe=True)
tok = db_op_counter.set(0)
try:
    await db.get("node", "n.1")
    assert db_op_counter.get() == 1
finally:
    db_op_counter.reset(tok)
```

Instrumented operations include the core CRUD surface plus adapter-specific
methods when wrapped: `traverse`, `find_connected_nodes`, and `find_iter`.
Counts reflect API-level calls (including cache hits on `get`), not individual
SQL statements.

### OpenTelemetry adapter

Install the optional extra:

```
pip install jvspatial[otel]
```

Then plug in the adapter. The application is responsible for
configuring the OTel SDK and exporters; the adapter targets whatever
`MeterProvider` is installed.

```python
from jvspatial.observability.otel import OpenTelemetryMetricsRecorder
from jvspatial.db import create_database

metrics = OpenTelemetryMetricsRecorder()
db = create_database(
    "sqlite",
    db_path="./app.db",
    observe=True,
    metrics=metrics,
)
```

If your application hasn't configured an OTel SDK, the meter API
emits no-ops — so the adapter is safe to wire up unconditionally and
only pays for emission when something is consuming it.

## Composition with caching

`create_database()` applies layers in this order, innermost first:

```
backend  (JsonDB / SQLiteDB / MongoDB / DynamoDB)
   |
   +— [if cache_get_size > 0]  CachingDatabase
                                    |
                                    +— [if observe]  ObservableDatabase
```

That ordering means the structured log line measures the
**user-visible** latency including cache hits and misses — which is
what SLO calculations need. The cache hit/miss distinction is
visible in two places: the `duration_ms` field (a hit is much
faster) and via `db.cache_stats()` if you reach through to the
inner cache wrapper.

## Serverless

The metrics layer itself works fine in serverless — every emission
is a synchronous in-process call. The structured log lines are
written through the standard `logging` module, which the runtime's
log forwarder will pick up.

The cache layer (`CachingDatabase`) is automatically disabled in
serverless mode because cold starts make a per-process cache useless;
that's a `CachingDatabase` policy, not an observability one.

See [serverless-mode.md](serverless-mode.md) § Caching in serverless for the
distinction between `CachingDatabase` (disabled) and `GraphContext` /
`LayeredCache` entity caches (not auto-disabled).

## See also

- [`stability.md`](stability.md) — `MetricsRecorder` Protocol is public.
- [`benchmarks.md`](benchmarks.md) — performance regression suite.
