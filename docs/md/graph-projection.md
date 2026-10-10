# Graph context for language-model inference

`await context.project_graph(...)` captures relationships around a starting node
for a language model to reason over. It returns stored facts, supporting paths,
and optional application-declared meanings. The application chooses its model
and inference workflow. Capture and rendering require no model provider.

## A complete dummy use case

Run `python -m examples.core.graph_projection_example` from an installed checkout.
The example creates `Root -> DemoApp -> categories -> domain nodes`, including:

- Two projects using a shared control board and supplier.
- A delayed supplier in a region with a flood warning.
- A dependency cycle between a board and its firmware.
- A candidate alternative whose qualification is explicitly unverified.
- A private supplier with a downstream region that the public policy excludes.

The public Harbor projection contains nine nodes and ten relationships. It gives
a model evidence for a possible supplier exposure, preserves the cycle, and does
not establish that flooding caused a delay or that the alternative is suitable.
One deterministic discovery path is retained per node; other observed edges
preserve shared dependencies. Actual language-model inference is not performed
by the example or the deterministic test suite.

```python
from jvspatial import ProjectionRequest, ProjectionScope, ProjectionSemantics

snapshot = await context.project_graph(
    ProjectionRequest(
        root_id=project.id,
        view="ontology",
        edge_types=("DependsOn", "SuppliedBy", "LocatedIn"),
        direction="out",
        max_depth=3,
        max_nodes=100,
        max_edges=200,
        max_candidates=1000,
        max_bytes=32768,
        execution_mode="native",
    ),
    scope=ProjectionScope(
        name="current application",
        node_query={"context.application_id": application.id},
        node_fields=("name", "status"),
    ),
    semantics=ProjectionSemantics(
        edge_types={"DependsOn": "Source requires target."},
        label_fields={"Project": "name"},
    ),
)
model_context = snapshot.render_text()
structured = snapshot.to_dict()
diagram = snapshot.render_mermaid()
```

Use `ProjectionScope.all(...)` only when the host explicitly intends full-store
reachability. An application root is an anchor, not an automatic security
boundary: outgoing or bidirectional edges can cross application branches.

## Views and configuration

All views contain nodes, edges, evidence paths, metadata, and expansion points.

| View | Additional representation |
| --- | --- |
| `relationships` | Typed graph facts and discovery paths. |
| `hierarchy` | Flat parent/child entries. `reference=true` identifies non-discovery edges, including shared children and cycles. The root is identified in metadata. |
| `ontology` | Meanings of represented node and edge types, marked `application_declared`. Missing descriptions are `null`; coverage is limited to represented types. |

A hierarchy follows the request's selected edge types; choose containment edges
when a containment hierarchy is intended. It preserves the underlying graph
identities and directed/bidirectional relationships.

| Control | Default | Meaning |
| --- | --- | --- |
| `direction` | `out` | `out`, `in`, or `both`; bidirectional edges can be followed in either direction. |
| `edge_types`, `node_types` | empty tuples | Exact stored discriminator filters; empty means any permitted type. Node filters also apply to the root. |
| `node_filter`, `edge_filter` | empty mappings | Record-path predicates; `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$exists`, `$regex`, `$and`, `$or`. Evaluated by the bounded-time in-memory matcher. |
| `node_fields`, `edge_fields` | `None` | Select a subset of the host scope's attribute allowlist; an empty tuple selects no attributes. |
| `max_depth` | 2 | Requested radius, maximum 20. Depth exhaustion alone is not a resource truncation. |
| `max_nodes`, `max_edges` | 100, 200 | Limits on emitted facts. |
| `max_candidates` | 1000 | Returned edge rows plus requested node records, including the root. Not physical database scan rows. |
| `max_edges_per_node` | 200 | Incident candidates examined per expanded node, including edges rejected by direction, scope, predicates, or policy. |
| `max_frontier` | 100 | Queued nodes awaiting expansion. |
| `page_size` | 50 | Edge-ID keyset page size, maximum 500. |
| `timeout_seconds` | 5 | Cooperative extraction deadline; cancellation propagates. Backend cancellation and raw-record size still depend on the adapter. |
| `max_bytes` | 32768 | Exact UTF-8 size cap for canonical JSON, minimum 4096. Rendering sizes are separately measurable and may differ. |
| `max_string`, `max_items`, `max_value_depth` | 512, 16, 4 | Attribute clipping limits. Per-field byte and visited-value budgets also bound nested containers. |
| `execution_mode` | `compatibility` | `native` requires backend-side adjacency paging; unsupported backends fail before reading. |

Order is deterministic BFS using ascending edge ID within each expansion.
Configurable global relevance ranking and exact degree counts are not provided.
Dotted attribute selections are represented as flat keys such as `risk.level`,
which avoids exposing sibling fields. Explicit null values are preserved.
Predicates on attributes require scope permission and per-record policy
permission to those attributes, even when they are omitted from the output.

## Visibility and safe model context

An optional `ProjectionAccess` implementation provides an async batch
`authorize(kind, records)` method. Return a mapping from each permitted record ID
to allowed attribute names. A missing ID or `None` denies the record. The granted
fields are intersected with the scope and request selections. Policy errors fail
the capture. Denied nodes do not enter the frontier, and denied edges do not
contribute to the result. Both endpoints of every emitted edge must be present.

Descriptions and labels are application declarations. Text rendering encodes
record strings as JSON data; Mermaid uses generated identifiers and escaped
labels. Applications must place stored content in a data context rather than
treating it as model instructions. Snapshot reuse does not confer authorization:
do not share captures across users or reuse them after permission changes without
a new authorized capture.

`snapshot.statistics` contains host-only candidate counts, abstract database operations, elapsed
time, and canonical bytes. It is excluded from automatic rendering because work
counts may disclose inaccessible cardinalities. One batch operation may make multiple backend calls; this metric is not a
transport round-trip count. SQL physical scan rows remain unknown. Hosts decide whether diagnostics may be exposed. Stop status and timing can still
reflect work on denied candidates; this API does not promise to eliminate such
side channels.

## Completeness and freshness

`meta.complete` means the permitted, filtered traversal within the requested
radius was examined without a resource stop. It does not claim global coverage
or an induced subgraph containing every edge between included nodes.
`detail_complete` and per-record `truncated_fields` separately identify clipped
attribute detail. Resource stop reasons include `max_nodes`, `max_edges`,
`max_candidates`, `max_frontier`, `max_edges_per_node`, `max_bytes`, and `timeout`.
An incident set exactly at the per-node cap is conservatively marked incomplete
unless a shorter page already demonstrated its end; exact counts are not read.

These are immutable captured results with **best-effort** reads. Multiple
database reads can observe concurrent edits. The fingerprint identifies the
request, not an atomic graph revision. Capture/read-finish timestamps report the
read interval. They do not promise retained historical data.

`snapshot.expansion_requests()` offers bounded new requests from included depth
boundaries or resource-stop locations. Execute them with the current scope and
access policy again. They are new live captures that may revisit records; they
are not resumptions against the earlier historical state.

## Backend and performance contract

`Database.graph_edge_page` uses a fixed incident-edge query, ascending ID sort,
and keyset limit. `supports_native_graph_paging` is true for SQLite, PostgreSQL,
and MongoDB; JSON and DynamoDB offer compatibility scans. Database wrappers
preserve the capability. Custom adapters may override the method and capability
together and must preserve filtering, ordering, and row limits.

Native paging bounds rows transferred to the engine. Index selection, physical
scan work, DB query execution, and the largest raw document fetched are not
bounded by response caps. Native SQL does not guarantee constant-time execution.
JSON compatibility paging can repeatedly scan the edge collection as pages and
expanded nodes increase. Use the native backends for larger graph workloads.
Retained historical snapshots and consistent-read transaction adapters are future
extensions; this release does not change transaction isolation.

Run `python -m examples.core.graph_projection_benchmark --output result.json` for
warm local extraction, rendering, ordinary CRUD, and JSON physical-file-read
measurements. Set `JVSPATIAL_PROJECTION_TEST_DSN` to include disposable PostgreSQL
schemas. See the [qualification report](../bench/2026-10-graph-projection.md) for measured
results and limits.
The feature adds no mandatory writes or workers to ordinary persistence.

## Testing and inference evaluation

`pytest tests/core/test_graph_projection.py` tests the realistic dummy graph,
configuration rejection, field and edge filters, scope, authorization failures,
revocation between captures, cycles, shared descendants, direction, closed
results, nested values, all resource caps, render escaping, cancellation, and
immutable results. Set `JVSPATIAL_PROJECTION_TEST_DSN` and
`JVSPATIAL_PROJECTION_MONGO_URI` for disposable live-backend tests.

For a downstream model evaluation, use the same model, prompt, and context budget
for record-only and relationship-context inputs. Ask which components share a
supplier, which project has a path to the flood-warning region, whether the
alternative is qualified, and what remains unknown in a truncated capture.
Score answer correctness, valid evidence IDs, unsupported claims, and abstention;
record latency and token usage from provider receipts. The shipped tests establish
evidence completeness, not a measured improvement in language-model inference.
