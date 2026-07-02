# jvspatial — Technical Specification

> **Purpose**: Authoritative technical contract for `jvspatial`. Describes what the library guarantees, what callers must not assume, and where the source of truth for each behavior lives. Cite this document by section number when justifying changes.
>
> **Scope**: Library behavior as of `jvspatial/version.py` → see file. This is a living spec; when behavior changes, this file must change in the same commit.
>
> **Companion documents**:
> - [PRD.md](PRD.md) — *why* the library exists (product context, users, success criteria)
> - [ROADMAP.md](ROADMAP.md) — forward-looking direction and known gaps
> - [CLAUDE.md](CLAUDE.md) — operational guidance for AI agents maintaining this repo
> - [docs/md/README.md](docs/md/README.md) — index of detailed how-to documentation
> - [LLM-CODING-GUIDE.md](LLM-CODING-GUIDE.md) — usage cookbook (code patterns for callers)

---

## Table of Contents

1. [Identity Model](#1-identity-model)
2. [Entity Hierarchy](#2-entity-hierarchy)
3. [Async Contract](#3-async-contract)
4. [Persistence Layer](#4-persistence-layer)
5. [Query Interface](#5-query-interface)
6. [Walker Traversal Semantics](#6-walker-traversal-semantics)
7. [GraphContext and Dependency Injection](#7-graphcontext-and-dependency-injection)
8. [API Surface](#8-api-surface)
9. [Authentication and Authorization](#9-authentication-and-authorization)
10. [Configuration and Environment](#10-configuration-and-environment)
11. [Serverless Constraints](#11-serverless-constraints)
12. [File Storage](#12-file-storage)
13. [Caching](#13-caching)
14. [Observability](#14-observability)
15. [Security Boundaries](#15-security-boundaries)
16. [Extension Points](#16-extension-points)
17. [Error Taxonomy](#17-error-taxonomy)
18. [Stability Tiers](#18-stability-tiers)

---

## 1. Identity Model

### 1.1 ID format

All persistable entities carry an `id` field with the format:

```
{type_code}.{entity_name}.{hex_id}
```

Where:

- `type_code` ∈ `{n, e, w, o}` (Node, Edge, Walker, Object)
- `entity_name` is the persisted discriminator (see 1.2)
- `hex_id` is the first 24 hex chars of `uuid.uuid4().hex`

**Source of truth**: `jvspatial/core/utils.py:11-22` (`generate_id`).

**Invariants**:
- `id` is `protected=True` — set at construction, cannot be reassigned after `__init__` completes (`jvspatial/core/entities/object.py:46-48`).
- `id` collisions are not detected at insertion; callers depending on uniqueness must coordinate generation. UUID4 collision probability is the only practical guarantee.
- `type_code` is per-class default: `o` for `Object`, `n` for `Node` (`jvspatial/core/entities/node.py:43`), `e` for `Edge` (`jvspatial/core/entities/edge.py:41`), `w` for `Walker` (`jvspatial/core/entities/walker.py:118`).

### 1.2 Entity name discriminator (`__entity_name__`)

The `entity_name` segment of the ID, and the persisted `entity` field, default to `cls.__name__`. Subclasses may override by setting `__entity_name__` as a `ClassVar`:

```python
class App(Node):
    __entity_name__: ClassVar[Optional[str]] = "HostApp"
```

**Source of truth**: `jvspatial/core/entities/object.py:35-44` (`_entity_name` classmethod).

**Resolution rule**: `cls.__dict__.get("__entity_name__") or cls.__name__`. Not inherited from a parent that set it — each subclass decides for itself.

**Use case**: disambiguating unrelated `Object` subtrees that share a Python class name (e.g. host-app `App` vs library-internal `App`) so they remain distinguishable at the storage layer.

**Implications**:
- `find_subclass_by_name` (`jvspatial/core/utils.py:58-89`) honors the override and caches positive hits. Negative hits are not cached (avoids bootstrap poisoning when classes are imported later).
- The persisted `entity` field tracks `_entity_name()` at creation time, not class name. Renaming a class without `__entity_name__` will orphan existing records.

### 1.3 Root singleton

`Root` is the canonical entry node for a graph. Its ID is fixed: `n.Root.root` (`jvspatial/core/entities/root.py`). Created via an async lock to guarantee single instantiation per database. All graph traversals can originate from `Root` by convention; not enforced.

---

## 2. Entity Hierarchy

```
AttributeMixin + pydantic.BaseModel
       │
   Object ─────── (type_code="o")
   │   │
   │   ├── Node ─────── (type_code="n")  ─── Root (singleton)
   │   │
   │   └── Edge ─────── (type_code="e")
   │
   Walker (AttributeMixin + BaseModel, not Object) ── (type_code="w")
```

### 2.1 Object — base persistable entity

`jvspatial/core/entities/object.py`. Provides:
- `id`, `entity`, `type_code` fields
- CRUD methods: `create()`, `get()`, `find()`, `save()`, `delete()`, `count()`, `export()`
- Context lookup: `set_context()`, `get_context()` (default via `get_default_context()`)
- Collection mapping via `get_collection_name()` → `{n: node, e: edge, o: object, w: walker}`

**Invariant**: `__setattr__` validates field names against the class hierarchy. Setting an undeclared attribute on an `Object` (post-init) is rejected. Prevents schema injection through attribute assignment.

### 2.2 Node — graph node

`jvspatial/core/entities/node.py:34+`. Adds:
- `edge_ids: List[str]` — transient in memory, persisted at the top level as `edges` (`Node._get_top_level_fields` line 55-60)
- `_visitor_ref: weakref` — currently visiting walker, transient
- `_visit_hooks: ClassVar` — populated by `__init_subclass__` from `@on_visit`-decorated methods (line 62+)

**Hooks**: methods decorated with `@on_visit(WalkerType | "string_name")` are registered per-class at class-creation time. String names allow forward references; resolved when the walker visits.

### 2.3 Edge — graph relationship

`jvspatial/core/entities/edge.py:29+`. Top-level persisted fields: `source: str`, `target: str`, `bidirectional: bool = True` (line 42-49).

**Direction**: `await edge.direction` returns `"both"` if `bidirectional`, else `"out"` (line 57-64). Asymmetric edges flow source → target.

### 2.4 Walker — traversal agent

`jvspatial/core/entities/walker.py:83+`. Walkers are **not** `Object` subclasses; they share `AttributeMixin` + `BaseModel`. Walkers are **not persisted to the database** by default — they exist for the lifetime of a traversal.

**Components** (composition, in `walker_components/`):
- `WalkerTrail` — visited node IDs, edge IDs, timestamps, optional per-step metadata
- `TraversalProtection` — enforces step/visit/time/queue limits
- `WalkerQueue` — FIFO queue with `max_queue_size` cap
- `WalkerEventSystem` — in-memory event bus for traversal lifecycle

**Default protection limits** (Walker class attrs):
- `max_steps`: 10 000
- `max_visits_per_node`: 100
- `max_execution_time`: 300 seconds
- `max_queue_size`: 1 000
- `protection_enabled`: True

These are *defaults* — subclasses or callers can override. Disabling protection (`protection_enabled=False`) is allowed but strongly discouraged in untrusted code paths.

### 2.5 Attribute system

`jvspatial/core/annotations` (re-exported as `jvspatial.core.annotations`):

| Flag | Effect |
|---|---|
| `protected=True` | Field cannot be reassigned after `__init__` completes |
| `transient=True` | Field is not persisted to the database |
| `private=True` | Field is hidden from `export()` output (and typically transient) |
| `default` / `default_factory` | Pydantic-style defaults |
| `description` | Documentation surfaced in OpenAPI schemas |

Indexed fields (`@attribute(indexed=True)`) and compound indexes (`@attribute(compound_index=...)`) inform backend index creation (where supported).

---

## 3. Async Contract

### 3.1 Async-only I/O

Every operation that touches the database, network, or file system is `async`. This includes — without exception:

- `Entity.create`, `Entity.get`, `Entity.find`, `Entity.find_one`, `Entity.save`, `Entity.delete`, `Entity.count`, `Entity.export`
- `Database.save`, `Database.get`, `Database.find`, `Database.delete`, `Database.count`, `Database.find_one`, `Database.find_many`, `Database.bulk_save`
- All Walker traversal methods (`spawn`, `step`, `walk`, `enqueue`, `pause`, `resume`)
- Storage backends (`upload`, `download`, `list_versions`, …)
- All API server lifecycle hooks (`on_startup`, `on_shutdown`, …)

### 3.2 Sync operations

Sync functions are reserved for **pure computation only**:

- `generate_id()`, `find_subclass_by_name()` — `jvspatial/core/utils.py`
- `get_collection_name()` — `jvspatial/core/entities/object.py:78`
- `is_serverless_mode()`, `detect_serverless_provider()` — `jvspatial/runtime/serverless.py`
- Walker trail read-only queries (`get_trail()`, `has_visited()`, `get_trail_summary()`)
- All `@attribute`-related helpers

Calling sync code from async is always safe. Calling async code from sync without an event loop is a programming error.

### 3.3 Blocking ops to avoid

- **Never** do synchronous file or network I/O inside an async handler — it blocks the event loop.
- **Never** spawn a thread to run an async coroutine — use `asyncio.create_task()` or `asyncio.gather()` instead.
- **Never** forget `await` on a database call — at best you receive a coroutine object; at worst you proceed with stale data.

### 3.4 Deferred saves (optional batching)

When `DeferredSaveMixin` is mixed into an entity *and* `deferred_saves_globally_allowed()` returns `True` (see §11.3), `await entity.save()` marks the entity dirty without writing. Persistence happens on explicit `await entity.flush()` or context exit.

**MRO requirement**: the mixin **must precede** the base class: `class MyEntity(DeferredSaveMixin, Node)` — not the reverse. Wrong MRO silently disables batching.

---

## 4. Persistence Layer

### 4.1 Database abstraction

`jvspatial/db/database.py:48+` — `Database` ABC. All adapters must implement:

| Method | Required | Description |
|---|---|---|
| `save(collection, data)` | Yes | Insert-or-replace by ID; returns saved record |
| `get(collection, id)` | Yes | Fetch by ID or `None` |
| `delete(collection, id)` | Yes | Idempotent delete by ID |
| `find(collection, query, *, limit, sort)` | Yes | Mongo-style query; returns list |
| `count(collection, query=None)` | Default impl | Default counts the result of `find`; adapters should override for efficiency |
| `find_one(collection, query)` | Default impl | First match or `None` |
| `find_many(collection, ids)` | Default impl | Bulk-fetch by ID; default is N sequential `get`s — adapters override for round-trip efficiency |
| `find_one_and_update` | Default impl | Read-modify-write; **not atomic** except where overridden (MongoDB) |
| `find_one_and_delete` | Default impl | Read-then-delete; **not atomic** except where overridden (MongoDB) |
| `bulk_save` | Default impl | Multi-record save; partial-success semantics vary by adapter |
| `begin_transaction` | Optional | Returns a transaction context manager if `supports_transactions=True` |

### 4.2 Capability flags

Adapters declare capabilities as class attributes:

- `supports_transactions: bool` — `True` for MongoDB (replica set); `False` for SQLite (best-effort), JSON, DynamoDB.

Callers branching on capabilities should test the flag, not the adapter class.

### 4.3 Built-in adapters

| Adapter | File | Transactions | Notes |
|---|---|---|---|
| JSON | `jvspatial/db/jsondb.py` | No | File-per-record, atomic writes (`_atomic.py`), per-file path locks (`_path_locks.py`) |
| SQLite | `jvspatial/db/sqlite.py` | No (single-conn fsync) | `aiosqlite`; Mongo→SQL via `SQLiteTranslator` |
| MongoDB | `jvspatial/db/mongodb.py` | Yes | `motor`; native bulk writes; native compound ops |
| DynamoDB | `jvspatial/db/dynamodb.py` | No | `aioboto3`; throttle-retry; `BatchGetItem` chunks of 100 |

### 4.4 Atomic IO (JSON)

`jvspatial/db/_atomic.py` provides crash-safe writes: temp file → `fsync` → `rename` → `fsync(directory)`. Per-file mutex via `PathLockManager` (`_path_locks.py`) serializes concurrent writes to the same record. Bounded LRU prevents lock-table growth.

### 4.5 Multi-database

`jvspatial/db/manager.py` — one "prime" database for core ops (auth, sessions, API keys), plus additional databases for specialized use. Auth state is **always** on the prime database; this cannot be relocated.

### 4.6 Schema migration

No built-in migration framework. Adapters do not enforce schemas. Adding optional fields with defaults is backward-compatible on read. Removing fields breaks existing records that still contain them. Application owners are responsible for migration scripts.

---

## 5. Query Interface

### 5.1 Mongo-style operators

`jvspatial/db/query.py` — unified query DSL across adapters. Supported operators:

| Operator | Meaning |
|---|---|
| `$eq`, `$ne` | Equality / inequality |
| `$gt`, `$gte`, `$lt`, `$lte` | Comparison |
| `$in`, `$nin` | Membership |
| `$exists` | Field presence |
| `$and`, `$or` | Logical combinators |
| `$regex` | Regex match (string fields) |

### 5.2 Pushdown vs in-memory

- **MongoDB**: native pushdown; queries run server-side.
- **SQLite**: translated to SQL via `SQLiteTranslator` (subset; complex `$or` chains may fall back).
- **DynamoDB**: limited pushdown via `Select=COUNT` and key conditions; remainder filtered client-side.
- **JSON**: full in-memory evaluation after loading matching collection.

### 5.3 Compiled query cache

`QueryEngine` caches compiled queries (default LRU size 1024, configurable per database via `query_cache_size`). Cache bounds prevent unbounded growth from dynamic query construction.

### 5.4 `Entity.find` field paths

Caller-facing queries on `Entity.find({...})` operate on the persisted document shape. Entity attributes (other than top-level fields like `id`, `entity`, `edges`, `source`, `target`, `bidirectional`) live under a `context` sub-object. Use `"context.field_name"` as the query key for attribute fields.

---

## 6. Walker Traversal Semantics

### 6.1 Lifecycle

1. Instantiate walker: `walker = MyWalker(...)`.
2. Begin: `await walker.spawn(start_node)` or `await walker.walk(start_node)`.
3. Per step: dequeue node, set visitor, run matching `@on_visit` hooks, optionally enqueue more nodes.
4. End: queue empty, `pause()` called, protection limit hit, or `WalkerTimeoutError` raised.

### 6.2 Visit hooks

- `@on_visit(NodeType)` on a Walker method — fires when the walker visits `NodeType` (or its subclass).
- `@on_visit(WalkerType)` on a Node method — fires when `WalkerType` visits *this* node.
- `@on_visit` with no target — fires for every visit.

Hooks are registered at class-creation time in `__init_subclass__` (`node.py:62`, `edge.py:66`).

### 6.3 Protection invariants

When `protection_enabled=True` (default):

- Step counter increments on every visit; exceeding `max_steps` raises `WalkerExecutionError`.
- Per-node visit counter increments on every visit; exceeding `max_visits_per_node` raises `InfiniteLoopError`.
- Wall-clock timer started at `spawn`; exceeding `max_execution_time` raises `WalkerTimeoutError`.
- Enqueue refuses when queue length would exceed `max_queue_size` (silent drop, logged).

Protection is *advisory* for safety, not for security — untrusted user input should not influence walker construction.

### 6.4 Trail tracking

`WalkerTrail` records `(node_id, edge_id, timestamp, node_type, queue_length, metadata)` for every visit (when `trail_enabled=True`). `max_trail_length=0` is unlimited; bounded by memory. In serverless deployments, trails do not persist across invocations.

### 6.5 Control flow

- `walker.pause()` — raises `TraversalPaused`; caller catches to suspend.
- `walker.skip()` — raises `TraversalSkipped`; advances to next queued node.
- `walker.resume()` — re-enters traversal from saved state.

### 6.6 Optional performance extensions (`walker.py`)

Defaults preserve §6.1 one-node-per-step semantics:

| Knob | Default | Behavior |
|------|---------|----------|
| `frontier_batch_size` | `1` | Max items dequeued per run-loop iteration |
| `prefetch_neighbors` | `False` | Bulk-fetch neighbors via `nodes_bulk` / `neighborhood` before hooks |
| `prefetch_depth` | `1` | Hops for prefetch (`>1` uses backend `traverse` when available) |
| `speculative_prefetch` | `False` | Warm entity cache for queued nodes while hooks execute |

Enabling prefetch may enqueue neighbors before hook-driven `visit()` calls; visit deduplication still follows protection / trail rules.

### 6.7 `Node.neighborhood` (`node.py`)

`await node.neighborhood(depth=k, direction=..., edge=..., node=..., limit=...)` returns hydrated `Node` instances within `k` hops. Postgres uses `Database.traverse` + `get_batch`; other backends use per-hop `nodes()` BFS.

---

## 7. GraphContext and Dependency Injection

`jvspatial/core/context.py` — `GraphContext` binds a `Database` + optional `Cache` + `PerformanceMonitor` to a scope.

### 7.1 Resolution order

When an entity needs a context, it resolves in this order:
1. Explicitly set via `await entity.set_context(ctx)`.
2. Default context: `get_default_context()` (singleton, lazily initialized from environment).

### 7.2 Scoping

`GraphContext` is request-scoped by convention. The API server installs a per-request context via middleware (`jvspatial/api/components/auth_middleware.py` and lifecycle), so endpoint handlers reach the correct database without manual injection.

### 7.3 Performance monitoring

`PerformanceMonitor` (within `GraphContext`) records:
- DB operation counts and latencies
- Hook execution counts and latencies
- Cache hits and misses

Surfaced via `observability/` for export to metrics sinks.

---

## 8. API Surface

### 8.1 Server class

`jvspatial/api/server.py` — composition of four mixins:

| Mixin | File | Concern |
|---|---|---|
| `AppFactoryMixin` | `api/server_app_factory.py` | Build FastAPI app, init DB, set up CORS |
| `RegistrationMixin` | `api/server_registration.py` | Register routes from `@endpoint`-decorated targets |
| `LifecycleMixin` | `api/server_lifecycle.py` | Startup/shutdown hooks, context wiring |
| `RunMixin` | `api/server_run.py` | Uvicorn invocation, host/port resolution |

### 8.2 `@endpoint` decorator

`jvspatial/api/decorators/route.py` — single decorator for both async functions and `Walker` subclasses:

```python
@endpoint("/users/{user_id}", methods=["GET"], auth=True, roles=["admin"])
async def get_user(user_id: str): ...

@endpoint("/walk", methods=["POST"])
class MyWalker(Walker):
    ...
```

**Parameters**:
- `path` — FastAPI path with parameters
- `methods` — HTTP methods list
- `auth: bool` — require authentication (default `False`)
- `roles: list[str]` — RBAC roles
- `webhook: bool` / `webhook_model` — webhook handler mode with signature verification
- `response` — response schema using `ResponseField` + `success_response()`

### 8.3 Deferred registry

Endpoints decorated at import time are collected in a deferred registry (`api/endpoints/registry.py`). The server resolves them at app-build time, after the database context is available. This allows entity-bound endpoints to be declared at module scope.

### 8.4 Built-in endpoints

When `auth_enabled=True`, the server registers `/auth/register`, `/auth/login`, `/auth/logout`, plus token refresh and password reset endpoints. With `auth_enabled=False`, no auth endpoints are registered.

OpenAPI docs at `/docs` and `/redoc` unless `JVSPATIAL_DOCS_DISABLED` is truthy (see §10.5).

---

## 9. Authentication and Authorization

### 9.1 Authentication mechanisms

- **JWT**: `PyJWT`-based. Secret required at startup (`jwt_secret` config or `JVSPATIAL_JWT_SECRET_KEY` env). Server **fails fast** on missing secret.
- **API keys**: SHA-256 hashed at rest, plaintext returned **only once** on creation. Verification uses `hmac.compare_digest` (constant-time).
- **Refresh tokens**: rotate on use; previous tokens invalidated.
- **Password reset**: `token_lookup` field provides O(1) lookup; constant-time comparison.

### 9.2 Authorization (RBAC)

`jvspatial/api/auth/rbac.py` — roles map to permission unions. Wildcard support (e.g. `users:*`). Admin-only routes enforced on `/status`, `/logs`, and `/graph` subtrees by default.

### 9.3 Session management

`SessionManager` tracks active sessions per user. **Per-process, in-memory** — true limits in multi-worker deployments are `limit × workers`. Document this when configuring session caps.

### 9.4 Logout blacklist

JWT tokens are blacklisted on logout. Blacklist storage is per-worker in default config. Cross-worker invalidation requires a shared blacklist store (caller-provided).

### 9.5 Webhook authentication

`jvspatial/api/integrations/webhooks/` — HMAC signature verification with constant-time comparison. Per-source secret rotation supported. Replay protection via timestamp window (configurable).

---

## 10. Configuration and Environment

### 10.1 ServerConfig

`jvspatial/api/config.py` — Pydantic model. Hierarchical groups:

```
ServerConfig(
    title, description, version, debug, docs_url, redoc_url,
    host, port, serverless_mode, deferred_task_provider,
    scheduler_enabled, scheduler_interval,
    database=DatabaseConfig(...),
    security=SecurityConfig(...),
    cors=CORSConfig(...),
    auth=AuthConfig(...),
    rate_limit=RateLimitConfig(...),
    file_storage=FileStorageConfig(...),
    webhook=WebhookConfig(...),
    proxy=ProxyConfig(...),
    log_level, startup_hooks, shutdown_hooks,
    graph_endpoint_enabled=True,
)
```

Flat keyword arguments (e.g. `Server(db_type=..., jwt_secret=...)`) are mapped to the appropriate group by a model validator (lines 103-128). The flat form is convenient; the hierarchical form is canonical.

### 10.2 Merge order

`Server(...)` arguments merge in this order (later wins):

1. `ServerConfig` defaults
2. Allowlisted `JVSPATIAL_*` environment variables (see `jvspatial/env_adapter.py`)
3. `config=` dict or keyword arguments

Unknown `JVSPATIAL_*` keys are rejected at startup to catch typos and removed settings.

### 10.3 Environment variable allowlist

`jvspatial/env_adapter.py` lists every accepted `JVSPATIAL_*` key with type coercion rules. The canonical reference is [docs/md/environment-keys-reference.md](docs/md/environment-keys-reference.md).

### 10.4 Database environment

`jvspatial/env.py` provides `resolve_db_paths()`, `parse_bool()`, and friends. Database type defaults:
- `JVSPATIAL_DB_TYPE` — backend selector
- `JVSPATIAL_DB_PATH` — backend-specific path or URI

### 10.5 Docs gating

`JVSPATIAL_DOCS_DISABLED` (truthy values: `1`, `true`, `yes`, `on`) disables `/docs`, `/redoc`, `/openapi.json`, and `/docs/oauth2-redirect` at app build time. CSP headers are relaxed only on docs paths to allow the Swagger UI CDN; app routes retain strict CSP.

**Source of truth**: `jvspatial/api/components/app_builder.py`.

---

## 11. Serverless Constraints

### 11.1 Detection precedence

`is_serverless_mode(config=None)` (`jvspatial/runtime/serverless.py:66-87`) resolves in this order:

1. Explicit `config.serverless_mode` if set (not `None`)
2. Same via `get_current_server()` when `config` is omitted
3. `SERVERLESS_MODE` env var (`true`/`1`/`yes`/`enabled`)
4. Auto-detection from platform env vars (Lambda, Azure Functions, Cloud Run, Vercel)

Detection results are memoized via `lru_cache`; tests call `reset_serverless_mode_cache()` between cases.

### 11.2 Mode-dependent behavior

| Behavior | Standard | Serverless |
|---|---|---|
| Deferred saves enabled by env | Yes (`JVSPATIAL_ENABLE_DEFERRED_SAVES`) | **No (forced off)** |
| Default JSON DB path | Working directory | `/tmp` (Lambda-writable) |
| bcrypt rounds | 12 | 10 (faster cold start) |
| Auto-create DB indexes | Yes | No (CloudWatch log cost) |
| JsonDB orphan cleanup | Yes | Skipped |
| Walker trail persistence | In-memory only | In-memory only (lost on cold start) |

### 11.3 Deferred task dispatch

`jvspatial/serverless/` — `dispatch_deferred_task(task_type, payload)` invokes a registered async handler out-of-band. On AWS, transport is Lambda async-invoke or EventBridge (configurable).

Register handlers with `@deferred_invoke_handler("task.name")`. Handlers **must be idempotent**; the framework provides no exactly-once guarantee.

### 11.4 Lambda Web Adapter

When LWA is detected, `Server` applies best-effort defaults for `AWS_LWA_PASS_THROUGH_PATH` and `AWS_LWA_INVOKE_MODE`. The LWA extension reads these *before* Python starts, so IaC should still set them explicitly for reliability.

---

## 12. File Storage

`jvspatial/storage/` — abstract `FileStorageInterface` (`interfaces/base.py`) with two built-in implementations:

| Adapter | File | Backing | Versioning |
|---|---|---|---|
| Local | `interfaces/local.py` | Filesystem | Version directory per file |
| S3 | `interfaces/s3.py` | AWS S3 | Native S3 versioning + multipart ≥8 MiB |

### 12.1 Security layer

- `storage/security/path_sanitizer.py` — five-stage validation: regex blocklist (11 patterns), normalization with re-check, hidden-file allowlist, symlink resolution, base-directory confinement.
- `storage/security/validator.py` — content-based MIME via `python-magic`. ~25 allowed types, 14 blocked types, 19 blocked extensions. Internal markers bypassed via metadata validation only (never user-supplied).

### 12.2 Upload contract

All uploads pass through `path_sanitizer` then `validator`. Failures raise `ValidationError` with `field_errors` populated. Successful uploads return a versioned descriptor.

### 12.3 S3 specifics

- Multipart upload threshold: 8 MiB (chunks of 8 MiB).
- Throttle retry on `ThrottlingException` with exponential backoff.
- Credentials required if `file_storage_enabled=True` and backend is `s3`.

---

## 13. Caching

`jvspatial/cache/` — pluggable cache layer.

### 13.1 Backends

| Backend | Use case |
|---|---|
| `memory` | Per-process LRU; default for single-instance deployments |
| `redis` | Shared cache across workers/instances |
| `layered` | Memory L1 + Redis L2; promotes hot keys to L1 |

### 13.2 Wrapping pattern

`jvspatial/db/_cache.py` provides a read-through wrapper for `Database`. Enabled per database via `cache_get_size` parameter in `create_database(...)`. Auto-invalidates on `save` and `delete`.

### 13.3 TTL and invalidation

TTL is per-cache-instance; default `None` (cache until eviction). Invalidation is event-driven: write operations on the wrapped database publish invalidation events. Cross-instance invalidation requires the Redis or layered backend.

---

## 14. Observability

`jvspatial/observability/` — metrics and tracing surface.

### 14.1 MetricsRecorder protocol

`MetricsRecorder` defines `record_db_op`, `record_hook`, `record_cache_event`. Implementations may push to Prometheus, StatsD, or any sink. The library provides:

- `NullRecorder` — default; no-op.
- OpenTelemetry adapter (`observability/otel.py`) — optional, requires `[otel]` extra.

### 14.2 Structured DB logging

`jvspatial/db/_observable.py` — wraps a `Database` to emit structured log records per op: `{op, collection, duration_ms, query_size, result_size}`. Configurable slow-query threshold (`slow_query_ms`) emits warnings.

### 14.3 GraphContext PerformanceMonitor

In-context counters for DB ops, hook execs, cache stats. Read at end-of-request to surface aggregate metrics.

---

## 15. Security Boundaries

### 15.1 User-input boundary

User input crosses the trust boundary at:
1. **HTTP request handlers** — validated by Pydantic at the FastAPI layer.
2. **`Entity.update()`** — validates all field names against the class hierarchy; rejects undeclared attributes (`object.py` setter).
3. **File uploads** — content-based MIME validation, not extension-based.
4. **Path inputs** — `path_sanitizer.py` before any filesystem access.

### 15.2 Constant-time comparisons

All secret/key/token/hash comparisons use `hmac.compare_digest`. Affected paths:
- API key verification
- Refresh token comparison
- Password reset token comparison
- Webhook HMAC signature verification
- Deferred-invoke secret comparison
- Legacy bcrypt fallback hash verification

Removing constant-time comparisons in favor of `==` is a security regression.

### 15.3 Security headers

`jvspatial/api/components/security_headers_middleware.py` injects:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Content-Security-Policy` — strict on app routes; relaxed only on `/docs`, `/redoc`, `/openapi.json` (CDN allowed).
- `Strict-Transport-Security` (HSTS) when HTTPS termination is configured.

### 15.4 CORS defaults

Default CORS is restrictive (no wildcards). Wildcard origins must be set explicitly and trigger a startup warning.

### 15.5 Secret handling

- JWT secret required at startup; empty/weak values rejected.
- S3 credentials required if file storage is enabled.
- API key secrets shown plaintext **only** on creation response; stored hashed.
- 500 error responses sanitize secret-bearing fields.

---

## 16. Extension Points

### 16.1 Custom databases

`register_database_type("name", factory_fn)` (`jvspatial/db/factory.py`) registers a custom adapter. The factory must return a `Database` subclass instance. After registration, callers use `create_database("name", ...)` like a built-in.

### 16.2 Endpoint registration

`@endpoint(...)` collects targets at import time. Either decorate functions or `Walker` subclasses. The framework registers routes at server build.

### 16.3 Hooks

`Server(...)` accepts lifecycle and event hooks:

| Hook | Fires on |
|---|---|
| `on_startup` | App boot, after DB ready |
| `on_shutdown` | App teardown |
| `on_admin_bootstrapped` | First admin user created |
| `on_user_registered` | New user creation |
| `on_enrich_current_user` | Per-request user enrichment |
| `on_password_reset_requested` | Password reset flow |

### 16.4 Deferred task handlers

`@deferred_invoke_handler("task.type")` registers an async handler. Handlers must be idempotent.

### 16.5 Custom storage backends

Implement `FileStorageInterface` (`storage/interfaces/base.py`) and register via the storage manager (`storage/managers/proxy.py`).

### 16.6 Middleware

`server.middleware_manager.add(...)` accepts any Starlette-compatible middleware.

### 16.7 Custom log levels

`jvspatial/logging/` permits adding domain levels (e.g. `AUDIT`, `SECURITY`, `TRACE`) above standard levels. See `docs/md/custom-log-levels.md`.

---

## 17. Error Taxonomy

`jvspatial/exceptions.py` centralizes all exceptions. Hierarchy:

```
JVSpatialError
├── EntityError
│   ├── EntityNotFoundError
│   │   ├── NodeNotFoundError
│   │   ├── EdgeNotFoundError
│   │   └── ObjectNotFoundError
│   └── DuplicateEntityError
├── ValidationError
│   └── FieldValidationError
├── ConfigurationError
│   ├── InvalidConfigurationError
│   └── MissingConfigurationError
├── DatabaseError
│   ├── ConnectionError
│   ├── QueryError
│   ├── TransactionError
│   └── VersionConflictError
├── GraphError
│   ├── InvalidGraphStructureError
│   ├── CircularReferenceError
│   └── EdgeConnectionError
├── WalkerError
│   ├── WalkerExecutionError
│   ├── WalkerTimeoutError
│   └── InfiniteLoopError
├── APIError (via jvspatial.api.exceptions)
│   ├── JVSpatialAPIException
│   ├── EndpointError
│   ├── ParameterError
│   ├── AuthenticationError
│   ├── AuthorizationError
│   ├── RateLimitError
│   ├── InvalidCredentialsError
│   └── RegistrationDisabledError
└── SecurityError
    └── PermissionDeniedError
```

Control-flow exceptions for walkers live in `jvspatial.core.entities`:
- `TraversalPaused` — caller catches to suspend traversal
- `TraversalSkipped` — caller catches to skip current node

### 17.1 Propagation rules

- Database errors propagate to the caller; entity methods may wrap with context.
- Validation errors raise `ValidationError` with `field_errors`. The API layer maps to HTTP 400.
- Authentication errors map to HTTP 401; authorization errors to HTTP 403.
- Walker errors are logged and surface in `walker.response["errors"]`; traversal halts.

---

## 18. Stability Tiers

`docs/md/stability.md` is the canonical tier reference. Summary:

| Tier | Guarantee |
|---|---|
| **Stable** | Public API. Breaking changes require a major version bump and two-version deprecation grace. |
| **Internal** | May change between minor versions. Documented for callers who need the detail, but not contracted. |
| **Experimental** | May change in any release. Opt-in only. Examples: `JsonDBTransaction(best_effort=True)`, some deferred-save edge cases. |

**Stable** includes (non-exhaustive): `Object`/`Node`/`Edge`/`Walker` public methods, `@endpoint` and `@attribute` decorators, `Database` ABC contract, `Server` constructor.

**Internal** includes: contents of `jvspatial/db/_atomic.py`, `_path_locks.py`, `_cache.py`, `_observable.py`; `jvspatial/api/components/*` implementation details; `jvspatial/storage/managers/*` internals.

**Experimental** includes: anything explicitly flagged in `docs/md/stability.md`.

Deprecations emit warnings via `jvspatial/utils/deprecation.py` (see file). Removal happens no sooner than two minor versions after the deprecation warning lands.

---

## Appendix A — Critical File Map

| Concern | Primary file |
|---|---|
| Identity / `__entity_name__` | `jvspatial/core/entities/object.py:35-44`, `jvspatial/core/utils.py:11-89` |
| Node model | `jvspatial/core/entities/node.py` |
| Edge model | `jvspatial/core/entities/edge.py` |
| Walker model | `jvspatial/core/entities/walker.py`, `walker_components/*` |
| Root singleton | `jvspatial/core/entities/root.py` |
| GraphContext | `jvspatial/core/context.py` |
| Database ABC | `jvspatial/db/database.py:48+` |
| Built-in DB adapters | `jvspatial/db/{jsondb,sqlite,mongodb,dynamodb}.py` |
| Query engine | `jvspatial/db/query.py` |
| Atomic IO | `jvspatial/db/_atomic.py` |
| Path locks | `jvspatial/db/_path_locks.py` |
| DB cache wrapper | `jvspatial/db/_cache.py` |
| DB observability wrapper | `jvspatial/db/_observable.py` |
| Server class | `jvspatial/api/server.py` |
| App builder + CSP/docs gating | `jvspatial/api/components/app_builder.py` |
| `@endpoint` decorator | `jvspatial/api/decorators/route.py` |
| Endpoint registry | `jvspatial/api/endpoints/registry.py` |
| Auth service | `jvspatial/api/auth/service.py` |
| RBAC | `jvspatial/api/auth/rbac.py` |
| API key service | `jvspatial/api/auth/api_key_service.py` |
| Config + env merge | `jvspatial/api/config.py`, `jvspatial/env.py`, `jvspatial/env_adapter.py` |
| Serverless detection | `jvspatial/runtime/serverless.py` |
| Deferred task dispatch | `jvspatial/serverless/deferred_invoke.py`, `serverless/tasks/*` |
| Storage interfaces | `jvspatial/storage/interfaces/{base,local,s3}.py` |
| Storage security | `jvspatial/storage/security/{path_sanitizer,validator}.py` |
| Cache backends | `jvspatial/cache/{base,memory,redis,layered}.py` |
| Observability | `jvspatial/observability/{metrics,otel}.py` |
| Logging service | `jvspatial/logging/{config,service,models}.py` |
| Exceptions | `jvspatial/exceptions.py`, `jvspatial/api/exceptions.py` |
| Version | `jvspatial/version.py` |

---

## Appendix B — Maintenance Checklist for Spec Changes

When code changes alter behavior described in this document:

1. Update the affected section, citing the new `file:line` if structure changed.
2. If the change is breaking, also update [ROADMAP.md](ROADMAP.md) (release notes) and [CHANGELOG.md](CHANGELOG.md).
3. If the change affects stability tier, also update [docs/md/stability.md](docs/md/stability.md).
4. If the change affects a security invariant (§15), also update [docs/md/security-review.md](docs/md/security-review.md).
5. Add a test that exercises the new behavior.
