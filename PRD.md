# jvspatial — Product Requirements Document

> **Purpose**: Capture *why* jvspatial exists, who it serves, and what success looks like. This is the product context for the technical contract in [SPEC.md](SPEC.md).
>
> **Audience**: Maintainers (human and AI), reviewers, future contributors evaluating whether a proposed change is in scope.
>
> **Status**: Living document. Update in the same commit as any change that alters scope, target users, or success criteria.

---

## 1. Positioning

jvspatial is an **async-first, serverless-compatible, object-spatial Python library** for building persistence and business-logic application layers on top of a graph data model.

It is *not*:

- A graph database engine. jvspatial layers a graph model on top of existing backends (MongoDB, SQLite, JSON files, DynamoDB) and unifies query semantics across them.
- A web framework. It builds on FastAPI; it does not replace it.
- A workflow engine. Walkers traverse data; they are not a generic task orchestrator.
- A UI library. Visualization helpers exist (DOT, Mermaid), but rendering is out of scope.

It *is*:

- A substrate for graph-native business logic, with an entity-centric API that hides storage details from domain code.
- A FastAPI integration layer that turns decorated entities and walkers into HTTP endpoints with consistent auth, validation, and observability.
- A serverless-aware library that adapts its defaults (deferred saves, index creation, hashing cost) to the deployment environment.

The library is inspired by Jaseci's object-spatial paradigm. The implementation is pure Python, async-throughout, and uses Pydantic v2 for schemas.

---

## 2. Target Users

Described by role, not by named product. jvspatial serves callers in three roles:

### 2.1 Backend engineers building graph-shaped applications

People modeling domains where relationships are first-class: knowledge graphs, social structures, agent memory, organizational hierarchies, recommendation systems, geographic networks.

**What they need**: an entity model with first-class edges, traversal primitives that respect graph semantics, async I/O so a request handler can fan out across the graph without blocking.

### 2.2 Platform teams building serverless APIs over graph data

People deploying graph-backed services to AWS Lambda, Google Cloud Run, Azure Functions, Vercel — environments that need stateless request handling, fast cold starts, and explicit boundaries between in-request work and deferred work.

**What they need**: serverless mode detection that flips opinionated defaults (deferred saves off, indexes off, lower bcrypt cost, `/tmp` DB paths), a deferred-task dispatcher that survives invocation boundaries, idempotency-friendly handler registration.

### 2.3 Library authors needing a persistence + traversal substrate

People building higher-level frameworks that ship a graph model to their own users. They want a foundation they can extend without forking — custom database backends, custom storage backends, custom auth flows, custom log levels.

**What they need**: stable extension points (`register_database_type`, `FileStorageInterface`, lifecycle hooks, deferred-task handlers), a documented stability contract so their downstream depends only on stable surface, and a clean separation between public API and internal helpers.

---

## 3. Core Value Propositions

| # | Value | What it means | Where it lives |
|---|---|---|---|
| 1 | **Unified query DSL across backends** | One Mongo-style query syntax works against JSON, SQLite, MongoDB, and DynamoDB. Switch backends without rewriting queries. | `jvspatial/db/query.py` |
| 2 | **Entity-centric API** | `Node.create()`, `Node.get()`, `node.save()` — domain code calls entity methods, never raw DB clients. | `jvspatial/core/entities/object.py` |
| 3 | **First-class walkers** | Graph traversal is a built-in primitive with infinite-loop protection, trail tracking, and event hooks. Not a hand-rolled BFS in every handler. | `jvspatial/core/entities/walker.py` |
| 4 | **Identity model with explicit discriminators** | Every entity carries `type_code.entity_name.uuid`. `__entity_name__` lets disjoint hierarchies coexist. | SPEC §1 |
| 5 | **Serverless ergonomics by default** | One env var (`SERVERLESS_MODE=true`) flips a coherent set of defaults — no scattered serverless special cases in application code. | `jvspatial/runtime/serverless.py` |
| 6 | **Security defaults that fail closed** | JWT secret required, constant-time secret comparisons, content-based file MIME validation, restrictive CORS, strict CSP on app routes, optional `/docs` gating. | SPEC §15 |
| 7 | **FastAPI integration without lock-in** | `@endpoint` exposes functions and walkers as routes. The underlying FastAPI app is accessible for middleware, custom routers, and lifecycle hooks. | `jvspatial/api/server.py` |
| 8 | **Observable by construction** | Structured DB op logs, `MetricsRecorder` protocol, GraphContext `PerformanceMonitor`, OpenTelemetry adapter. | `jvspatial/observability/`, `jvspatial/db/_observable.py` |

---

## 4. Non-Goals

Explicit out-of-scope statements. These represent decisions, not gaps.

| Non-goal | Why |
|---|---|
| Replace a real graph database (Neo4j, ArangoDB, Neptune) | jvspatial layers on document stores; it does not implement graph-native storage, indexes, or query planning. Use a graph DB when the workload demands it. |
| Provide a graph traversal query language | Walkers are imperative async Python. There is no Cypher or Gremlin equivalent and no plan to add one. |
| Synchronous API surface | The library is async-only by design. A sync wrapper would force `asyncio.run` per call and degrade performance. Callers stuck in sync contexts should run jvspatial in a worker. |
| Distributed transactions across backends | Multi-database operations are best-effort. Only single-backend transactions are supported (and only where the backend natively supports them — MongoDB replica sets). |
| Built-in caching strategy beyond the wrappers provided | We provide memory, redis, layered. Beyond that, callers compose their own. |
| Schema migrations | No migration framework. Adding optional fields with defaults is forward-safe; everything else is the caller's responsibility. |
| UI / dashboard | Graph export to DOT/Mermaid is provided. Rendering, visualization tooling, and a Web UI are downstream. |
| First-party multi-tenancy primitives | Multi-tenancy is doable via context scoping but is not codified. Tenant isolation is a caller responsibility. |

---

## 5. Constraints

### 5.1 Language and runtime

- Python 3.9+ supported (3.8 declared in `pyproject.toml` classifiers but should be considered legacy).
- Pydantic v2 is required — Pydantic v1 compatibility is not maintained.
- FastAPI / Starlette pinned to versions that retain the `Router(on_startup, on_shutdown)` API (Starlette `<1.0.0`).

### 5.2 Concurrency

- Async-only I/O. Every database call, network call, and file-system call is a coroutine.
- No global mutable state that survives a request, except the database manager and module-level registries (decorator-collected endpoints, deferred task handlers). All such state is initialized at app build, not per-request.
- Sessions, rate-limit counters, and JWT blacklists are **per-process / per-worker** by default. Cross-worker sharing requires Redis or a similar shared store.

### 5.3 Serverless

- Cold-start cost is a budget, not a goal. Reduced bcrypt rounds and skipped index creation in serverless mode reflect this.
- No assumption that any in-memory state survives across invocations. Walker trails, sessions, and caches reset.
- `/tmp` is the only writable filesystem on Lambda; JSON DB defaults route there.

### 5.4 Security

- Secrets are never logged. 500 error responses are sanitized.
- Comparison of any secret, key, token, or hash uses `hmac.compare_digest`. This is non-negotiable.
- New auth flows, key types, or token formats require a security review (see [SECURITY.md](SECURITY.md) and `docs/md/security-review.md`).

### 5.5 Compatibility

- The `jvspatial/__init__.py` `__all__` export list is the public contract. Submodule import paths are *not* stable; promote symbols through the top-level package.
- Breaking changes to public API require a major version bump (post-1.0) or a minor bump (pre-1.0) with a `**BREAKING**` callout in [CHANGELOG.md](CHANGELOG.md).
- Deprecations follow the policy in [docs/md/stability.md](docs/md/stability.md): mark with `@deprecated`, warn for at least one minor cycle, then remove.

---

## 6. Success Criteria

### 6.1 Qualitative

- **A caller building a new graph-backed service can get to a working CRUD endpoint in under 30 minutes**, following [docs/md/quick-start-guide.md](docs/md/quick-start-guide.md) and one of the [examples/api/](examples/api/) reference implementations, without reading any source code.
- **A caller can switch backends (JSON → SQLite → MongoDB → DynamoDB) without rewriting queries or entities** — only configuration changes.
- **A caller deploying to Lambda does not need to write Lambda-specific code**, beyond the entry adapter for their function. Defaults adapt; deferred work has a single registration point.
- **An AI agent maintaining the library can locate the right code path from a single CLAUDE.md read**, without having to crawl the docs tree.
- **A security reviewer can audit the trust boundary by reading SPEC §15** and confirm every claim against `file:line` citations.

### 6.2 Quantitative

Quantitative budgets are deferred to the upcoming foundation audit. Placeholders that will be filled in during that pass:

- p50 / p99 latency budgets for `Entity.get`, `Entity.find`, `Walker.walk` against each backend.
- Cold-start envelope on Lambda (target: well under the platform's 1s default timeout for HTTP API + Lambda).
- Memory footprint per active walker.
- Test-coverage gate (current floor: 60%; CHANGELOG implies a tighter floor is desired but not yet enforced).
- Benchmark regression detection: the existing pytest-benchmark suite must remain green in CI.

---

## 7. Stability Tiers (Ratification)

The library distinguishes three tiers; [docs/md/stability.md](docs/md/stability.md) is the canonical reference.

| Tier | Contract | Examples |
|---|---|---|
| **Stable / Public** | Names in `jvspatial.__all__`. Breaking changes require a major version bump (post-1.0) or a minor bump with a `**BREAKING**` callout (pre-1.0). At least one deprecation cycle before removal. | `Object`, `Node`, `Edge`, `Walker`, `Root`, `GraphContext`, `Server`, `ServerConfig`, `Database`, `@endpoint`, `@attribute`, `DeferredSaveMixin`, `is_serverless_mode`, `dispatch_deferred_task`, `MetricsRecorder`. |
| **Internal** | Module path begins with `_` or is documented internal. Can change in any release without notice. Callers should not import directly. | `jvspatial/db/_atomic.py`, `_path_locks.py`, `_cache.py`, `_observable.py`; `jvspatial/api/server_*.py`; `jvspatial/runtime/lwa.py`. |
| **Experimental** | Public but opt-in. May change or be removed in any minor release. Marked via `@experimental` decorator, emits a once-per-process warning. | `JsonDBTransaction(best_effort=True)`. |

The PRD ratifies this tiering. Promotion of a feature from experimental to stable, or demotion of an internal helper to public, is a product decision and must be reflected here as well as in `docs/md/stability.md`.

---

## 8. Decision Boundaries

When evaluating proposed changes, apply these decision rules:

| Question | Answer |
|---|---|
| Does this change introduce a new sync API on a code path that touches I/O? | **Reject.** Async-only is a core constraint (§5.2). |
| Does this change broaden the CORS default to a wildcard, or remove a constant-time comparison? | **Reject.** Security defaults must fail closed (§5.4). |
| Does this change add a feature that duplicates an existing public API? | **Reject** unless the existing API is being deprecated in the same change. |
| Does this change add a new env var? | **Allowed**, but must be added to the `JVSPATIAL_*` allowlist (`jvspatial/env_adapter.py`) and documented in [docs/md/environment-keys-reference.md](docs/md/environment-keys-reference.md). |
| Does this change add a new public name? | **Allowed**, but must be added to `__all__` and [docs/md/stability.md](docs/md/stability.md). |
| Does this change extend the database ABC contract? | **Allowed** only if all four built-in adapters implement it or fall through a sensible default. |
| Does this change couple jvspatial to a specific upstream consumer? | **Reject.** jvspatial is a foundation; consumer-specific logic lives in the consumer. |

---

## 9. Open Questions

Items the PRD does not yet decide. These are inputs to the upcoming foundation audit.

- Quantitative success criteria (§6.2 placeholders).
- Whether session state, rate-limit counters, and JWT blacklists should have first-party shared-storage adapters or remain per-worker by default.
- Whether the multi-database manager should grow first-class tenant scoping primitives or remain a thin registry.
- Whether `count()` semantics should guarantee consistency vs. allow eventual count from DynamoDB.
- Whether the experimental `JsonDBTransaction(best_effort=True)` should be promoted, demoted, or removed.

---

## 10. Living-Document Discipline

This PRD is authored to remain accurate over time. Update rules:

1. Adding a public API → update §3 (value props) and §7 (stability tiers).
2. Adding a non-goal → update §4 with one-line justification.
3. Changing a constraint → update §5 and reflect in [SPEC.md](SPEC.md) where contract changes.
4. Closing an open question → move from §9 into the appropriate section.

Any code change that contradicts a current statement here must update this file in the same commit, or document an exception in [ROADMAP.md](ROADMAP.md).
