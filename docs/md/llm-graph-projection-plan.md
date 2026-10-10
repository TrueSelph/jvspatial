# Graph projections for language-model inference

Status: implemented for version 0.2.0; see [usage](graph-projection.md) and
[qualification](../bench/2026-10-graph-projection.md). The original design intent
and acceptance criteria below are retained with the implementation decisions
recorded at the end.

Date: 2026-10-10

Baseline: main at `f645f20`.

## Purpose

Add a separate, read-only query method that renders existing graph relationships
into structured context for language models. A caller chooses a standpoint and
receives relationship hierarchies or an ontology snapshot that a model can use
to make inferences, with paths back to the underlying records.

JV Spatial owns graph extraction, declared semantic metadata, bounded
representation, and rendering. The consuming application supplies scope, access
rules, domain descriptions, and the language model. Running inference is outside
this feature's execution path.

The capability is opt-in and uses the existing persistence model. It requires no
model provider, embeddings service, background worker, or additional write on
ordinary CRUD operations. Performance claims must be established by measurement.

## User-facing operation

The central operation is: "Show me the meaningful relationships around this
entity, within this scope and budget, in a form a model can understand."

One extraction contract supports three views:

| View | Meaning |
| --- | --- |
| Relationship graph | Selected entities, typed and directed relationships, and paths from the standpoint. |
| Hierarchy | A rooted presentation following explicitly selected relationship types, with cycles and shared children represented as references. |
| Ontology snapshot | A captured relationship graph accompanied by descriptions of the entity and relationship types represented in it. |

A hierarchy is a view over a graph, not a conversion of every relationship into
containment. The application declares which relationships express containment,
dependency, membership, or other meanings. Shared descendants retain their
identity, and a cycle is never silently discarded or presented as a tree edge.

An ontology snapshot records declared meanings and observed associations. It
does not assert that arbitrary connections imply causation, equivalence, or
transitivity. Type descriptions missing from the application remain unspecified.
Descriptions derived from the returned subset must not be presented as a complete
inventory of the application's schema.

## API shape

```python
# Public API implemented in version 0.2.0.
projection = await context.project_graph(
    request,
    scope=application_scope,
    access=application_access,
    semantics=application_semantics,
)

structured = projection.to_dict()
text = projection.render_text()
mermaid = projection.render_mermaid()
```

The request specifies a starting node, relationship direction and type filters,
node predicates, field selection, depth, ordering, and resource budgets. Initial
implementation supports one starting node. Multiple standpoints can follow once
ordering and combined-budget semantics are defined.

Scope and access are trusted application inputs, not authority supplied by the
model's request. Full-store access requires an explicit application choice.

This is a bounded library operation, not a general traversal query language.
It does not execute Walker visit hooks or arbitrary model-supplied Python. Existing
query and traversal behavior remains governed by its current public contracts.

## Canonical result

The structured representation is the source for every renderer. It includes:

- Stable node and edge IDs, stored entity discriminators, edge endpoints, and
  directed or bidirectional semantics.
- Explicitly selected node and edge attributes, with truncation markers.
- Optional application-provided labels and semantic descriptions, identified as
  declarations rather than inferred facts.
- Bounded supporting paths that explain inclusion. The initial default retains
  one deterministic discovery path per node; it does not enumerate all paths.
- The starting point, applied filters, scope identifier, ordering, and format
  version, without exposing sensitive scope or policy internals.
- Capture time, read interval, and the actual consistency guarantee.
- Completeness relative to the requested view, stop reasons, and optional
  continuation information.
- Work accounting available from the backend and the projection engine, with
  unknown physical scan costs represented as unknown.

The initial edge policy is traversal edges: it includes selected relationships
examined during expansion. It does not claim to contain every edge between the
returned nodes. Every emitted edge must have both endpoints in the result.
Authorized frontier entries may indicate further exploration without emitting
dangling edges or revealing inaccessible IDs.

Text output preserves IDs, relationship meanings, and evidence references in a
compact form. Mermaid output is for inspection and derives from exactly the same
payload. Rendering must escape labels and must never initiate database reads.
Stored content is represented as data; the consuming application determines how
to place that data in a model context without treating it as instructions.

## Snapshot and continuation semantics

In the first release, "snapshot" means an immutable captured result. It does not
by itself mean every record was read at one atomic database moment. Results must
label best-effort versus backend-supported consistent reads accurately.

Subsequent live expansion produces another capture and can observe graph changes.
It must not claim to expand an earlier historical state. A continuation binds to
the request, scope, ordering, and format version, has bounded state and lifetime,
and is validated before use. It must not carry unbounded frontier or visited sets
in a client token. If resumable state exceeds its budget, report that continuation
is unavailable and allow a new bounded query from an authorized frontier node.

Retained historical generations, cross-request repeatable reads, and incremental
snapshot maintenance are separate future work. Ordinary lifecycle events are
not a durable committed change stream.

## Resource and access contracts

Set explicit limits for returned nodes, returned edges, candidate records,
per-node expansion, frontier size, depth, path count, elapsed time, and serialized
bytes. Bound nested objects and list values as well as strings. Token estimates
may be supplied by an optional tokenizer; bytes are the portable output budget.

Use paged adjacency reads, deterministic ordering, and batched node fetching.
Exact degree counts are optional. Do not inherit entity-name priorities from
the visualization BFS. Application priorities are explicit and must fit the
execution budget; global relevance ranking is outside the initial contract.

Distinguish engine limits from backend work guarantees. A strict mode may run
only where the selected backend operations support the required execution
controls. Other backends can offer a disclosed scan-based compatibility mode.
No silent full-scan fallback is permitted under a strict work guarantee.
Timeout and cancellation behavior must be qualified for each supported adapter.

Apply access checks before an entity enters the frontier or contributes to an
exposed relationship, path, count, or summary. Field projection uses allowlists.
Batch access decisions where possible. Denied intermediate nodes cannot serve
as hidden bridges. A budget-exhausted result may contain fewer permitted records
than requested; it must not refill indefinitely. Recheck current permissions
when continuing or exposing cached results, and avoid metadata that reveals
hidden records or counts.

## Implementation sequence

1. **Contract and required primitive qualification.** Finalize request/result
   models, direction and filtering semantics, capability checks, ordering,
   completeness, and consistency labels. Add failing tests for defects in any
   existing primitives selected for reuse. Resolve filter loss, unbounded reads,
   and graph-boundary behavior on those paths before using them.
2. **Bounded extraction.** Implement the read-only projection operation and
   canonical payload. Start semantic tests on JSON; qualify strict execution on
   backends with the necessary paged operations. Cover access before expansion,
   field selection, paths, cycles, and resource stop reasons.
3. **Views and renderers.** Deliver relationship, hierarchy, and ontology views,
   compact text and Mermaid renderers, and bounded progressive exploration.
   Reuse extraction results across renderers. Publish API docs, examples, and
   explicit backend guarantees together.
4. **Qualification and release.** Measure projection cost, normal CRUD overhead,
   and model usefulness. Update PRD, SPEC, stability documentation, public exports,
   CHANGELOG, and security-review entries alongside the relevant implementation.

All three views belong to the initial feature. Broader abstraction through
precomputed summaries, community detection, embedding ranking, retained snapshot
generations, and model-generated inference remains outside this implementation.

## Acceptance criteria

- Type, direction, and predicate filters have equivalent meaning on every
  supported execution path. Unsupported strict operations fail explicitly.
- Every returned edge has returned endpoints. Shared descendants, self-loops,
  cycles, and multiple relationship types preserve their meaning.
- Hierarchy output follows declared relations. A partial exploration never
  asserts global absence or complete coverage.
- Denied nodes, edges, and fields do not contribute to visible paths, aggregates,
  renderings, or continuations. Permissions are rechecked on continued access.
- High-degree hubs, large frontiers, deeply nested values, and large lists stop
  within the advertised engine limits, with appropriate stop reasons.
- Concurrent writes and deleted records yield behavior consistent with the
  advertised read guarantee. Captured results remain immutable.
- Query instrumentation separates returned rows, fetched candidates, backend
  calls, bytes, and physical scan work where measurable. Test graph growth with
  a fixed local neighborhood to identify total-database dependencies.
- Baseline CRUD and ordinary traversal benchmarks quantify overhead with the
  feature unused. No performance improvement is claimed from output caps alone.
- On a small fixed evaluation set, compare record-only context with projected
  relationship context using the same model and context budget. Measure inference
  correctness, evidence-path accuracy, unsupported claims, abstention under
  truncation, latency, and context size. Examples include dependency chains,
  shared dependencies, hierarchy interpretation, and incomplete evidence.

## Source findings motivating the plan

Verified on the baseline commit:

- `core/graph_expansion.py` loads all incident edges before the BFS edge cap,
  computes exact degrees, and can return edges outside its node result.
- `core/entities/node.py` does not forward the requested edge filter in the
  `neighborhood` backend-traversal path.
- `db/jsondb.py` loads collection records before applying a query result limit.
- `core/graph_payload.py` leaves lists unbounded during context trimming.
- `db/postgres.py` applies recursive traversal deduplication and result limiting
  after expansion; the existing transaction opener does not establish an explicit
  repeatable-read contract.
- `core/graph.py` exports through full node and edge collection reads.

These findings identify qualification work, not permission to change unrelated
public APIs. Reuse and remediation must preserve documented compatibility.

## Final implementation decisions

- A separate extraction engine uses raw paged adjacency and batched fresh node
  reads. The older visualization/traversal helpers remain unchanged because they
  cannot provide this contract without broader compatibility work.
- `native` means backend-side adjacency ordering and row limiting. It explicitly
  does not promise bounded physical scan work, query execution, or raw record
  size. Compatibility mode discloses scan-based behavior. There is no misleading
  strict-work guarantee.
- Results capture best-effort reads. Expansion requests are new live captures
  under current scope and access rules. Retained generations, snapshot caches,
  and historical continuations are deferred.
- One discovery path per node bounds path growth; other captured edges preserve
  cycles and shared descendants. Hierarchy and ontology use the same facts.
- Engine statistics remain host-only, outside model rendering, because rejected
  candidate counts could disclose inaccessible cardinalities. Database operations
  count abstract adapter calls rather than transport round trips.
- Qualification uses realistic deterministic evidence questions and an independent
  traversal oracle. Actual model inference quality is left to downstream provider
  evaluation; this release makes no measured inference-improvement claim.
- Optional tokenizers, custom relevance ranking, and temporal predicates are
  deferred. Canonical bytes, field selection, supported predicates, and nested
  detail limits form the initial configuration contract.
