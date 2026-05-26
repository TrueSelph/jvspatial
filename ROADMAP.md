# jvspatial — Roadmap

> **Purpose**: Forward-looking maintenance direction. Captures current focus, known gaps and tech debt, areas under active hardening, and the release process. Not a feature wishlist — every entry has a citation or a justification.
>
> **Audience**: Maintainers planning the next pass. AI agents looking for "what should I work on next" should start here.
>
> **Status**: Living document. Update when scope shifts, when a known gap is closed, or when a new area enters active hardening.

---

## 1. Current Focus

Derived from recent commit trajectory ([CHANGELOG.md](CHANGELOG.md), `git log`).

### 1.1 Security hardening (active)

Recent waves have systematically eliminated constant-time-comparison gaps, fail-open auth defaults, and CSP holes. Continuing work:

- Maintain the audit cadence from `docs/md/security-review.md`. Each new auth flow or secret-touching path requires a review entry.
- Keep `JVSPATIAL_DOCS_DISABLED` as the standard production posture and ensure new app routes inherit strict CSP.
- Per-path CSP / docs gating: monitor for new routes added under `/docs` or `/openapi.json` namespaces.

### 1.2 Performance and bulk APIs (active)

- `find_many`, `bulk_save`, native `count()` pushdown landed in 0.0.7. Continue:
- Native bulk-update equivalents on backends that support them (Mongo `bulk_write`, SQLite `executemany UPDATE`).
- Continue surfacing slow-query telemetry via the observability layer; tune `slow_query_ms` defaults per backend.

### 1.3 Observability (active)

- `MetricsRecorder` protocol and OTEL adapter shipped in 0.0.7. Continue:
- Expand the per-op metric set (cache hits, hook latencies, walker step counts) beyond DB ops.
- Validate OTEL adapter against a real OTLP collector and add an integration test.

### 1.4 Stability contract enforcement (active)

- The public / internal / experimental tiers in `docs/md/stability.md` are now defined. Continue:
- Audit every public name in `jvspatial/__init__.py` for tier annotation.
- Wire `@experimental` warnings to any opt-in surface still missing them.

---

## 2. Known Gaps and Tech Debt

Items called out by SPEC audit (this docs pass) and prior work. Each carries a code-path citation.

### 2.1 Schema migration story is implicit

No migration framework. Field removals or renames break existing records silently. Adapters do not enforce schemas.

- **Decision needed**: ship a thin migration helper or document the per-application pattern.
- **Location**: cross-cutting; would touch `jvspatial/core/entities/object.py` field handling and `jvspatial/db/*` adapters.

### 2.2 Multi-database transactions are best-effort only

Only MongoDB supports ACID transactions. Cross-backend operations have no built-in coordination.

- **Decision needed**: document the limit explicitly in handler patterns or build an opt-in saga primitive.
- **Location**: `jvspatial/db/transaction.py`, `jvspatial/db/database.py:48+`.

### 2.3 Session state, rate-limit counters, JWT blacklist are per-worker

In multi-worker deployments, configured limits multiply by worker count. Cross-worker invalidation requires a shared store the library does not ship.

- **Decision needed**: provide first-party Redis-backed adapters for these stores or remain caller-owned.
- **Location**: `jvspatial/api/auth/enhanced.py` (SessionManager), `jvspatial/api/middleware/rate_limit*.py`.

### 2.4 `count()` consistency varies by backend

DynamoDB `count()` is eventually consistent; MongoDB and SQLite are strongly consistent; JsonDB is read-at-call-time.

- **Decision needed**: document the divergence per adapter, or add a `consistency=` argument.
- **Location**: `jvspatial/db/database.py:144`, per-backend overrides.

### 2.5 Walker trail does not persist across serverless invocations

By design (in-memory only). Long-running traversals across cold-starts cannot resume.

- **Decision needed**: add an optional persistent-trail adapter or accept the limit explicitly.
- **Location**: `jvspatial/core/entities/walker_components/walker_trail.py`.

### 2.6 Quantitative success criteria are unset

[PRD §6.2](PRD.md#62-quantitative) lists placeholders for latency, cold-start, and memory budgets. The upcoming foundation audit must fill these in.

### 2.7 Legacy `LLM-CODING-GUIDE.md` overlap with `docs/md/`

The legacy file contains code patterns that duplicate parts of `docs/md/quick-start-guide.md`, `entity-reference.md`, and others. Consider deprecating sections that are fully covered elsewhere.

- **Location**: [LLM-CODING-GUIDE.md](LLM-CODING-GUIDE.md).

### 2.8 Python 3.8 declared but not really supported

`pyproject.toml` classifiers include Python 3.8, but several features (notably `typing.Literal` and `ParamSpec` usage) prefer 3.9+. Either confirm 3.8 support with CI coverage or drop the classifier.

- **Location**: `pyproject.toml`.

### 2.9 Experimental status of `JsonDBTransaction(best_effort=True)` unresolved

[PRD §9](PRD.md#9-open-questions) flags this. Promote, demote, or remove.

- **Location**: `jvspatial/db/transaction.py`.

---

## 3. Areas Under Active Hardening

Code paths receiving sustained attention. Changes here warrant elevated review.

| Area | Why | Recent changes |
|---|---|---|
| `jvspatial/api/auth/*` | Auth touches every request; security regressions are high-blast-radius. | 0.0.7 hardening wave; ongoing per-flow reviews. |
| `jvspatial/storage/security/*` | File-upload trust boundary; path traversal is a known threat surface. | Internal-marker handling, validator extension to markdown files. |
| `jvspatial/db/_atomic.py`, `_path_locks.py` | Crash safety and concurrent-write correctness. | 0.0.7 atomic-write introduction; benchmark coverage added. |
| `jvspatial/runtime/serverless.py` | Detection precedence + mode-dependent defaults; subtle changes have wide effects. | 0.0.7 LWA env defaults, bcrypt rounds adjustment. |
| `jvspatial/db/_observable.py`, `jvspatial/observability/*` | Public log-field schema is part of the stability contract. | 0.0.7 introduction; field-set changes require deprecation. |
| `jvspatial/core/entities/walker.py` and `walker_components/*` | Protection limits prevent DOS; subclass extension surface. | Ongoing; trail-tracking refinements. |

---

## 4. Versioning and Release Policy

Authoritative process lives in [RELEASING.md](RELEASING.md). Summary:

- Version is read from `jvspatial/version.py`; the release workflow auto-creates the tag.
- Breaking changes pre-1.0 require a `**BREAKING**` callout in [CHANGELOG.md](CHANGELOG.md) and a one-cycle deprecation where reasonable.
- Deprecation pattern: `@deprecated(replacement=..., remove_in=...)` from `jvspatial/utils/deprecation.py`. Emits a once-per-process `DeprecationWarning`.
- Removal happens at the earliest in the second minor release after deprecation.

Stability tier reference: [docs/md/stability.md](docs/md/stability.md).

---

## 5. Out-of-Scope (Reaffirmed)

These items appeared in past planning discussions and remain out of scope. Listed so they are not reopened without a deliberate decision.

| Item | Rejected because |
|---|---|
| Built-in graph query language (Cypher / Gremlin equivalent) | Walkers are imperative async Python by design (PRD §4). |
| Synchronous API surface | Library is async-only (PRD §5.2). |
| Built-in dashboard / web UI | Visualization helpers (DOT, Mermaid) are sufficient; rendering is downstream. |
| First-party multi-tenancy primitives | Tenant isolation is caller-owned through context scoping. |

---

## 6. How to Use This Roadmap

- **Adding a new gap**: include the code-path citation and the decision needed. Do not list aspirations without a justification.
- **Closing a gap**: remove the entry from §2 in the same commit that lands the fix. Add a corresponding line to [CHANGELOG.md](CHANGELOG.md).
- **Promoting a focus area**: move from §2 (Gaps) into §1 (Current Focus) when sustained work begins.
- **Reaffirming out-of-scope**: append to §5 with the rejecting rationale.

The roadmap is for orientation. It is not a backlog and not a contract. Commitments live in CHANGELOG and milestones.
