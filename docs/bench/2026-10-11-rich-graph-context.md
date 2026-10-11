# Rich graph context qualification — 2026-10-11

Baseline: dev `621b77998c1a459dbb1158791e28e57c2fb438fa`. Changes extend the
existing projection engine; the package version remains `0.1.1` and release notes
remain under Unreleased. Local tests do not establish model inference quality.

## Compatibility and disclosure

Frozen-clock format 1 fixtures cover canonical data, text, Mermaid, request
fingerprints and expansion requests in all three views. No profile and an empty
profile preserve that output. Rich captures use opt-in format 2 and retain current
scope/field grants, closed endpoints, no expansion through denied nodes, fresh
best-effort reads, work/detail/byte limits and error/cancellation behavior.

The rooted operational example and independent assertions cover two prerequisites,
a mitigation scoped to one prerequisite, an unverified alternative, cycles/shared
descendants, recorded due dates, stale/conflicting observations, foreign partitions,
denied records/fields, and custom persisted discriminators. Evidence is recorded
data; coverage explicitly leaves decision sufficiency unassessed. Same-record
enrichment performs no additional database operations versus equivalent selected
fields. Missing, clipped or unauthorized evidence/selector inputs stay unresolved;
only referenced relationship definitions are published.

JSON, file-backed SQLite, disposable PostgreSQL 16 and MongoDB 8.0 are exercised.
SQLite cache/observability wrappers retain native capture behavior. DynamoDB's
existing compatibility contract is unchanged; live AWS capacity and throttling
are unqualified. Physical scans and raw-record memory remain backend limits.

## Reproducible paired capture probes

Run `python -m examples.core.rich_graph_context_benchmark`. The synthetic rooted
sparse ternary tree and hub fixtures are seeded outside timing in separate local
SQLite files. Each fixture gets two warm-up captures, then 15 alternating pairs
of fresh captures. Three consecutive executions are retained in
[raw measurements](2026-10-11-rich-graph-context-results.json). Runs use identical
selected fields, candidate budgets and topology caps; rich mode additionally
attaches states, provenance and schema-qualified relationship meanings. Text
rendering is measured separately. No model calls, tokens, physical scan counts,
cold starts or production concurrency are measured.

Values below are medians across the three run-level measurements. Overhead is
the median of each run's paired ratio, so it need not equal the ratio of the
aggregated timings. p95 uses sorted sample index `int(.95 * (rounds - 1))`.

| Shape / candidates | Plain capture ms | Rich capture ms | Plain / rich p95 ms | Median overhead | Plain / rich render ms | DB operations |
| --- | ---: | ---: | --- | ---: | --- | ---: |
| Sparse / 100 | 8.779 | 9.284 | 10.507 / 14.733 | 7.11% | 0.433 / 0.933 | 30 |
| Sparse / 1,000 | 171.091 | 183.509 | 264.916 / 235.570 | 6.06% | 4.302 / 8.750 | 287 |
| Hub / 100 | 2.899 | 3.294 | 3.107 / 3.608 | 18.37% | 0.433 / 0.931 | 3 |
| Hub / 1,000 | 26.815 | 30.290 | 44.822 / 35.493 | 14.25% | 4.831 / 10.271 | 21 |

Database operations, candidates, nodes and edges match the equivalent-field
baseline in every case. Abstract database operations are not transport round trips.
Rich canonical bytes are 54,343 / 565,918 for sparse budgets and 60,253 / 597,554
for hubs; plain bytes are 24,992 / 275,536 and 26,156 / 258,356. Rich rendered
text is 54,767 / 570,192 and 60,747 / 602,548 bytes. No fields clip under these
2 MB requests. A fixed smaller cap can fit less topology because metadata counts
toward the cap; the tests verify closure and exact canonical bytes at small caps.

The run-level hub/100 overheads were 13.03%, 18.37% and 26.39%. One run exceeds
20%; the median does not, and a repeatable greater-than-20% regression was not
observed across the three executions. These short local timings are variable;
use the raw runs when judging overhead rather than claiming a strict latency SLA.
The implementation prepares selectors/field declarations once per capture, avoids
copying the node map for each new endpoint, clips simple values directly with
legacy parity tests, and reuses immutable per-record JSON during final serialization.
The latter adds a bounded serialized-record cache inside the capture budget.

## Repository gates

- Console `pytest --cov=jvspatial`: 2,744 passed, 22 skipped, 70.31% statement
  coverage on Python 3.12.9. Native PostgreSQL/MongoDB projection tests ran.
  Skips include unavailable Redis/psutil and adapter-specific cases.
- Focused console projection run: 223 passed; the later full suite also includes
  aggregate-bound and intrinsic-selector regressions added after that run.
  `python -m pytest` compatibility/real-entity subset: 6 passed.
- Full `pre-commit run --all-files`: passed, including formatting, lint, typing,
  JSON/YAML and secret detection. The raw result's baseline uses its short commit
  ID because secret detection falsely classified the full public Git hash.
- `pytest tests/benchmarks --benchmark-only`: 21 passed, 4 intentionally skipped
  non-benchmark recorders; includes three rich-view cases and PostgreSQL cases.
- Wheel and source package built at `0.1.1`. The wheel installed into a separate
  target directory, and a smoke capture outside the source checkout verified
  public exports and format 1/2 behavior.

CI is a separate remote gate triggered by the authorized push to dev.
Downstream fixed-prompt/model trials should assess prerequisite direction,
mitigation scope, evidence citations, conflicts and honest unknowns; they have
not been performed by this library qualification.
