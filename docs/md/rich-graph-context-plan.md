# Rich graph context configuration — implementation plan

Status: implemented and locally qualified; downstream model trial deferred. Date: 2026-10-11.
Evidence and remaining limits: [qualification report](../bench/2026-10-11-rich-graph-context.md).
Baseline: dev commit `621b77998c1a459dbb1158791e28e57c2fb438fa`.

## Objective and boundaries

Extend `GraphContext.project_graph` so hosts can configure a bounded selection
of operational facts, declared relationship meanings, and evidence metadata.
Models should distinguish stored facts, application declarations, unavailable
detail, and conclusions requiring further evidence.

This extends the existing projection machinery; it adds no second graph engine,
model execution, automatic readiness scoring, domain-specific fields, persisted
snapshot records, background workers, or database migrations. Hosts continue to
own partition membership, current principal permissions, field permissions,
schema definitions, installed application contracts, and model workflows.

## Verified starting point

The current public surface and guarantees are in SPEC §6.9 and
`docs/md/graph-projection.md`:

- `ProjectionRequest` selects fields, types, filters, radius and work/detail caps.
- `ProjectionScope` supplies a trusted flat field allowlist and membership rules.
- `ProjectionAccess.authorize` supplies per-record field grants before expansion.
- `_selected` already supports flat dotted paths and preserves explicit nulls.
  A missing selected field is silently absent; clipping yields `truncated_fields`.
- `ProjectionSemantics` supplies string meanings by node/edge discriminator and
  label fields. It cannot distinguish semantic roles within one edge class.
- `complete` describes permitted traversal within the radius; `detail_complete`
  concerns clipping. Neither evaluates question sufficiency or factual truth.
- Captures are immutable best-effort multi-read results, not atomic generations.

Primary implementation locations: `jvspatial/core/graph_projection.py`,
`jvspatial/core/context.py`, public exports, and existing projection tests/example.

## Proposed public contract

Add an optional trusted keyword argument, leaving existing calls valid:

```python
await context.project_graph(
    request,
    scope=scope,
    access=access,
    semantics=semantics,
    context_config=context_config,  # new; optional host configuration
)
```

Proposed new exported Pydantic configuration types:

| Type | Purpose |
| --- | --- |
| `ProjectionContextConfig` | Host-selected profile ID/revision and per-node/per-edge type field declarations. No global profile registry or caller-supplied executable configuration. |
| `ProjectionField` | Exact context path, optional label/description/data-type/unit hints, deterministic priority and tighter clipping caps. Hints describe values; they do not coerce or certify them. |
| `ProjectionEvidence` | Optional binding from a projected field to same-record source, observation, verification-state and revision paths. Values are copied as recorded. |
| `ProjectionRelation` | Bounded, application-declared relationship definition with an ID, description, direction wording, optional inverse wording and declarative selectors. |

Extend `ProjectionSemantics` with optional `relation_rules`, preserving existing
`node_types`, `edge_types` and `label_fields`. Relationship declarations stay in
the existing semantics surface rather than being duplicated in context config.

Configuration models use `extra="forbid"`, validate duplicate paths/IDs, bound
type/field/rule counts and description sizes, and reject malformed paths,
unsupported predicates and invalid caps. Revalidate and detach nested mutable
inputs before the first await, as the existing capture already does.

### Field selection and detail

Field declarations are not permission grants. Effective projection fields are
the intersection of host scope, per-record access, profile selection, and any
explicit request selection. Without a profile, retain today's selection rules.
Requests cannot widen a profile or scope. Explicit empty field tuples retain
their current meaning: no attribute values or field-derived evidence.

For a configured entity type, its declared paths provide profile defaults.
Unconfigured types retain legacy defaults; hosts can declare an empty profile
for a type to select no detail. Reject configured data/selector/evidence paths
outside the scope before database reads. Per-record grants still narrow them.
Do not support wildcard selection or automatic inclusion of entire containers.

Keep dotted keys flat. A declaration for `risk.level` never grants its siblings.
Treat parent and child paths as exact grants, not implicit interchangeable
permissions. Preserve null, missing, empty string, zero and false separately.

Field-specific limits can only tighten global request caps. Apply deterministic
priority ordering with path-name tie breaks in rich mode. Existing canonical
byte, candidate, radius, timeout and nested-value caps remain authoritative.
Richer detail can reduce the topology fitting in a fixed byte budget; report
that honestly rather than promising unchanged topology or raising caps silently.

### Relationship semantics

Each rule matches an exact stored edge discriminator and optional predicates on
selected, authorized edge attributes. Optional endpoint selectors may inspect
only selected, authorized attributes of included endpoints. They cause no joins,
extra traversal or schema discovery. Reuse the supported bounded predicate
matcher, including regex timeouts.

This allows a shared edge class to carry separately declared roles such as
prerequisite, mitigation or alternative without hardcoding those words in core.
Hosts qualify rules using recorded schema identity/revision where necessary;
the framework never derives a meaning from a field name or class-name spelling.

Zero matching rules means no specialized meaning. Multiple matching rules yield
an explicit unresolved declaration; never choose a rule by list order. When an
input is omitted, denied or truncated, do not resolve a rule from its hidden or
partial raw value. Retain the generic edge-type meaning as a fallback.

Publish only definitions referenced by emitted relationships, marked
`application_declared`. Do not export the entire host rule catalogue. Preserve
stored edge direction separately from declared inverse wording and traversal
direction. Declared conditions are descriptive data, not executable logic or
claims that the conditions hold.

### Evidence and freshness

MVP evidence bindings copy only authorized, selected same-record paths. Source
identifiers are opaque recorded values, not automatic authority or links to
fetch. Related evidence records must enter through ordinary permitted traversal
or a separate host read; a scalar source ID never bypasses endpoint access.

For each projected fact, include references to its captured record ID and exact
field path, plus whatever source/observation/verification/revision values are
actually present. If an auxiliary path is unavailable, omit its key/value and
use a generic unresolved-evidence marker without naming the unavailable path.
Never manufacture verification, confidence, timestamps, canonical URLs or an
atomic revision. Capture time, record modification time and observation time
remain distinct. An explicitly stored confidence value is labeled as recorded,
not calibrated by the library.

Initially avoid enrichment callbacks, external lookups and cross-record joins.
The host can already place selected supporting content in bounded fields and
can perform follow-up reads under its own broker and access contract.

### Coverage and payload versioning

Default calls continue producing canonical format version 1, with unchanged
field shapes and semantics. A nonempty rich context configuration or relation
rule set opts into format version 2. No existing key is removed or reinterpreted.

Version 2 adds:

- Optional profile ID/revision chosen by the host, not a permissions fingerprint.
- Per-record field states for selected AND granted paths only: `present`, `null`,
  `missing`, `truncated`. Do not identify denied paths or denied records.
- Authorized field descriptions/evidence and per-edge declaration references.
- Referenced relationship definitions in ontology view, with edge meanings also
  available to the other views so choosing a view does not lose matched meaning.
- Coverage metadata stating `requested_radius`, selected-detail coverage, and
  `decision_sufficiency="not_assessed"`. The library does not judge whether a
  business question can be answered.

Keep `complete`, `detail_complete`, `stop_reasons`, `truncated_fields`, paths and
expansion points with their existing meanings. No denied cardinalities or
internal work statistics enter model output. Missing detail is not evidence of
absence, and a complete traversal does not certify readiness or global coverage.

Validate v2 in all renderers. Text output must retain new meaning/evidence/
coverage rather than silently discarding it. Mermaid can remain topology-focused
with safe labels. All descriptions and stored excerpts remain escaped data,
never model instructions. All metadata participates in exact canonical byte
accounting; final trimming must remove dangling definition/evidence references
and retain closed edge endpoints and valid paths. Expansion requests contain
only request configuration; hosts explicitly resupply context config, semantics,
scope and current authorization for every new live capture.

## Implementation sequence

| Step | Owned files/responsibility | Completion criterion |
| --- | --- | --- |
| 1. Lock contract with tests | New `tests/core/test_graph_projection_context.py`; existing legacy tests | Specify v1 parity, rich schemas, missing/null distinctions, denied selectors/evidence, ambiguous rules and byte-limit closure before implementation. |
| 2. Add typed configuration | `core/graph_projection.py`, `core/context.py`, `core/__init__.py`, top-level `__init__.py` | Optional keyword forwarding, detached validation, bounded declarations, exported public types; old calls unchanged. |
| 3. Implement safe detail and evidence | Capture selection/clipping internals, field authorization intersections | Per-type defaults and tighter caps; metadata only from authorized selected data; no additional DB operations for same-record enrichment. |
| 4. Implement relation meanings and v2 | Semantics resolution, finalization and renderers | Deterministic selectors, no hidden/partial-value inference, referenced definitions only, exact byte enforcement and valid trimming. |
| 5. Qualify realistic fixtures/performance | Existing projection example/benchmark and new tests | Correct current, missing, stale and conflicting recorded facts; revocation and partition isolation; measured capture/render/payload overhead. |
| 6. Document and downstream trial | SPEC §6.9, PRD §3/§7, stability doc, core README, projection guide, docs index, CHANGELOG Unreleased | Explicit public contract, migration example, backend caveats and independently attributed deterministic versus model evidence. |

Implementation should start on an isolated `codex/rich-graph-context` branch
based on the then-current `dev`; inspect the diff from this baseline first.
Do not modify the active dev checkout or unrelated release work. Feature work stays under Unreleased. The user subsequently authorized committing
and pushing these qualified changes to dev; versioning, publishing and deployment
remain separate.

## Validation matrix and gates

1. **Compatibility:** all existing projection tests; v1 fixture parity for
   structured JSON, text, Mermaid, fingerprints and expansion requests under a
   frozen clock. Test all views and top-level public imports. Rich config is
   immutable/detached and rejects unknown keys.
2. **Authorization:** independent entity and field denial; hidden intermediary;
   readable foreign-partition endpoint; inaccessible evidence and selector
   fields; same field key in two schema namespaces; revocation between captures;
   policy exceptions and cancellation. No unauthorized value, path, rule ID,
   evidence reference, count or sibling field reaches output or renderers.
3. **Correctness:** false/zero/null/missing, nested fields, multibyte strings,
   unsupported/nonfinite values, duplicate declarations, conflicting rules,
   direction/inverse wording, custom entity discriminators, stale source data,
   conflicting stored observations, cycles and shared descendants. Recorded
   provenance does not certify truth; conflicts remain visible facts.
4. **Budgets:** every existing cap with rich metadata enabled; tiny-byte captures;
   clipped selector values; definition/evidence overhead; no dangling references
   after trimming; selected-field states cannot escape caps. Descriptions and
   evidence counts are bounded before serialization.
5. **Backends:** JSON first; SQLite and disposable PostgreSQL native captures;
   MongoDB when available; compatibility/native rejection contracts for remaining
   adapters and wrappers. No database ABC change is expected. Adapter tests
   must verify no unscoped full graph export was introduced.
6. **Performance:** compare legacy versus configured rich capture at 100/1,000
   candidate budgets and sparse/high-degree fixtures; report warm median/p95,
   DB operations, canonical/rendered bytes and clipping rates. Same-record
   enrichment must add zero DB operations versus equivalent plain field
   selection. Reject unexplained repeatable >20% median capture overhead versus
   an equivalent-field baseline; establish a repeatable baseline before judging.
   Raw record size, physical scans and downstream model tokens remain separate.
7. **Repository gates:** focused tests, `pytest -q`, coverage suite, pre-commit
   all-files, and projection benchmarks. Run console `pytest` as well as the
   focused module invocation where source-import behavior matters. Document
   unavailable infrastructure rather than treating skipped tests as qualification.

Acceptance fixture: a rooted project has two prerequisites, one mitigation and
an unverified alternative. Record a due date, operational state, evidence source,
observation date and schema-qualified relationship meanings. Include missing,
stale and conflicting evidence variants plus denied and foreign-partition links.
Deterministic tests must prove the exact authorized facts and limits in every
variant. A downstream model trial must separately score supported conclusions,
relationship direction, mitigation scope, honest unknowns and evidence citations
under a fixed prompt/model/budget. The library tests do not claim model quality.

## Risks and deliberately deferred work

- Rich content increases prompt-injection exposure and payload size: preserve
  data encoding, explicit field selection and limits; host prompts enforce the
  distinction between instructions and captured data.
- Semantic selection can leak hidden attributes: evaluate only selected,
  authorized, untruncated inputs and publish referenced declarations only.
- Same-record evidence is deliberately limited. Add an async batch enrichment
  protocol only after a measured use case requires it, with separately specified
  authorization, timeout, source closure and per-call budgets.
- Persistent generations, atomic snapshots, relevance-ranked traversal, logical
  inference and automatic constraint/readiness evaluation are separate projects.
  Record revisions are useful evidence, not a replacement for atomic reads.
- Existing PRD/ROADMAP statements outside projection contain historical drift.
  Trust source for this plan; update projection contracts with code and avoid an
  unrelated documentation rewrite.

## Definition of done

Legacy users see no changed defaults. Opted-in hosts can configure useful facts,
field-level evidence and qualified relationship meanings without weakening scope
or access. Rich output describes exactly which authorized detail was captured,
what was clipped/missing, and what the library cannot certify. Tests and measured
backend evidence support those claims, public docs match code, and a downstream
trial is reported separately from extraction correctness.
