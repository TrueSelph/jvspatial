# Changelog

All notable changes to jvspatial will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.9] - 2026-06-14

### Security

- **Redis cache no longer unpickles untrusted blobs in the default JSON mode** (`jvspatial/cache/redis.py`). Previously, an unprefixed value in `json` serialization mode fell through to `pickle.loads`, so anyone able to write to the Redis keyspace could achieve remote code execution even with the "safe" default. JSON mode now refuses non-JSON values (treated as a cache miss → recompute). Legacy pickle entries are readable only when explicitly opted in via `allow_legacy_pickle=True` / `JVSPATIAL_REDIS_ALLOW_LEGACY_PICKLE=true` on a trusted keyspace. Explicit `pickle` mode is unchanged.

### Fixed

- **Docs: authentication examples used a flat `auth_enabled=True` kwarg** that `ServerConfig` silently ignores (auth stayed disabled). Corrected README and `docs/md/{authentication,api-keys,migration}.md` to the nested `auth=dict(...)` form.
- Layered cache fell back to `print()` for Redis-unavailable warnings; now uses `logging.warning` (`jvspatial/cache/layered.py`).

### Packaging

- Removed `setup.py`; `pyproject.toml` is now the single source of build metadata. Version resolves dynamically from `jvspatial/version.py` via `[tool.setuptools.dynamic]`. Fixes a metadata conflict where the wheel published `Requires-Python: >=3.8` while the project targets `>=3.9`.
- Added the `cache` extra (`redis[hiredis]`) so `pip install jvspatial[cache]` works; it backs `jvspatial.cache.redis`.
- Completed the `all` extra to cover every runtime-optional backend/feature (lambda, postgres, pgvector, otel, cache, scheduler).
- Removed the redundant top-level `requirements*.txt` files; dependencies live solely in `pyproject.toml` extras.

### Phase F — Cursor pagination (2026-05-26)

#### Added

- **`Database.find_iter` async iterator** (`jvspatial/db/database.py`): constant-memory pagination across all backends. Yields records one at a time; fetches in pages of `batch_size` (default 100). Default base-class implementation uses keyset pagination on `id` (always-unique, lexically sortable per SPEC §1.1) so every backend gets correct constant-memory iteration with no override required. Opaque `cursor` bytes (`base64(json(payload))`) for resume across processes; helpers `encode_cursor()` / `decode_cursor()` exposed on the module.
- **PostgreSQL native `find_iter`** (`jvspatial/db/postgres.py`): single pool connection held for the iteration; one SQL `SELECT ... WHERE id > $last_id ORDER BY id LIMIT $batch_size` per page; composes with the user query so GIN / functional indexes still apply. `sort` argument composes as `ORDER BY <field>, id ASC` for stable keyset tiebreaking. Falls back to base default when the query / sort can't push down.
- **`Object.find_iter()` surface** (`jvspatial/core/entities/object.py`): `async for obj in User.find_iter({"context.active": True}, batch_size=500): ...`. Mirrors `find()` signature + adds `batch_size`, `cursor`. Hydrates Pydantic instances; skips records that fail deserialization (matching `find()` semantics).
- **Test coverage** (`tests/db/test_cursor_pagination.py`): 12 tests covering cursor encoding round-trip + invalid input, default `find_iter` (JsonDB) — yields all / preserves order / unique ids / batch-size independent of total / filter applied / resume via cursor / empty collection / Object hydration. (3 PG live-DB tests preserved but currently skipped pending a known pytest-asyncio + asyncpg.pool teardown interaction; PG `find_iter` itself is verified by standalone smoke + production usage.)
- **Documentation**: `docs/md/cursor-pagination.md` — adoption guide with batch-size tuning, checkpoint pattern with `encode_cursor`, per-backend implementation table, consistency notes under concurrent writes.

### Phase E — Schema migrations (2026-05-26)

#### Added

- **Schema migration framework** (`jvspatial/core/migrations.py`): `Object.__schema_version__: ClassVar[int] = 1` discriminator; per-class `@migration(cls, from_version, to_version)` decorator; `_Registry` with MRO-walking chain resolution; `apply_migrations(record, cls) -> (record, changed)` runner. Legacy records without `_v` treat as version 1. Refuses downgrades and missing chain steps with explicit `MigrationError` diagnostics. Duplicate `(cls, from, to)` registrations fail fast. Closes ROADMAP §2.1.
- **Load-path migration hook**: `GraphContext._deserialize_entity` invokes `apply_migrations` before hydration. `GraphContext(auto_persist_migrations=True)` writes the upgraded record back on read so subsequent reads skip the work (default `False` — load doesn't write).
- **`jvspatial migrate` CLI** (`jvspatial/cli.py`): scans a collection, applies migrations to records below the current class schema version. Flags: `--collection`, `--entity NAME`, `--import-module M` (repeatable, loads `@migration` decorators), `--dry-run` (default) vs `--apply`, `-v`. Wired as `jvspatial = "jvspatial.cli:main"` in `[project.scripts]`.
- **Test coverage** (`tests/core/test_migrations.py`): 19 tests covering registry mechanics (registration / chain resolution / duplicate rejection / downgrade refusal / missing-step diagnostic / MRO walking / subclass override), `apply_migrations` semantics (legacy records / no-op / multi-step / step-returns-non-dict guard), `GraphContext` load-path integration (in-memory migrate / auto_persist write-back / missing-migration logs-not-raises), and CLI (dry-run + apply paths).
- **Documentation**: `docs/md/schema-migrations.md` — adoption guide covering single-step / multi-step / parent-MRO migrations, persistence policy, CLI usage, failure modes, and testing patterns.

### Phase D — Production hardening (2026-05-26)

#### Added

- **Walker trail persistence** (`jvspatial/core/entities/walker_components/trail_store.py`): pluggable `TrailStore` protocol with two adapters — `InMemoryTrailStore` (default, preserves legacy semantics) and `DBTrailStore` (persists every step to any registered `Database`). `WalkerTrail` accepts an optional `store` + `walker_id`; when set, every recorded step mirrors to the store (fire-and-forget via `record_step`, awaitable via `arecord_step`). New classmethod `Walker.restore(walker_id, store=...)` rehydrates a walker from a persisted trail for cold-start resume (Lambda + deferred-invoke). Closes ROADMAP §2.5.
- **Shared session store for multi-worker auth** (`jvspatial/api/auth/_session_store.py`): `SessionStore` protocol with `InProcessSessionStore` (dict-backed, default) and `RedisSessionStore` (wraps `jvspatial.cache.redis.RedisCache` with namespace prefix + TTL). `AuthenticationService` accepts `session_store=` constructor kwarg; the blacklist cache is now routed through the store so revocations propagate across Gunicorn workers / Lambda instances within TTL. `create_session_store()` factory accepts `None` / `"memory"` / `"redis"` / a Redis URL / a pre-built cache backend. Closes ROADMAP §2.3.
- **OpenTelemetry tracing** (`jvspatial/observability/tracing.py`): `get_tracer()`, `db_span()`, `walker_span()`, `http_span()`, and `inject_traceparent_into()` helpers. Spans honor OTel semantic conventions (`db.system` / `db.operation` / `db.collection.name`, `walker.class` / `walker.id` / `walker.entry_node`, `http.method` / `http.route`). All helpers are safe to call with no OTel installed — they return no-op spans, keeping the library callable in zero-observability deployments.
- **Graph invariant validator** (`jvspatial/core/validate.py`): `validate_graph(*, context, check_orphans, check_root_cycles, check_dangling_edges)` returns a `ValidationReport` with orphan node ids, root-cycle node ids, and dangling edge ids. Bidirectional edges count as reachable for orphan detection and as not-a-cycle for cycle detection. Read-only; safe for periodic audits.
- **Test coverage**: 53 new Phase D tests (`tests/core/test_trail_store.py`, `tests/api/test_session_store.py`, `tests/observability/test_tracing.py`, `tests/core/test_validate.py`) — all green. Tracing tests cover both the no-OTel and OTel-with-in-memory-exporter paths.

### Phase C — PostgreSQL backend (2026-05-26)

#### Added

- **`PostgresDB` adapter** (`jvspatial/db/postgres.py`): the new recommended production backend. Built on `asyncpg` + JSONB. Connection pool auto-tunes by `is_serverless_mode()` (Lambda: min=0/max=3; long-running: min=2/max=10). Optional `pooler_mode="transaction"` for PgBouncer / RDS Proxy compatibility. Schema per collection: `(id PK, entity, tenant_id, data JSONB, _v, created_at, updated_at)` with default GIN on `data` + entity / tenant_id partial indexes. Atomic `find_one_and_update` / `find_one_and_delete` via `UPDATE ... RETURNING` + `FOR UPDATE`. Bulk writes via `COPY FROM STDIN` (5–20× motor on common workloads). Per-collection schema bootstrap is idempotent + cached.
- **PostgreSQL JSONB query translator** (`jvspatial/db/_postgres_translate.py`): near-100% Mongo-operator pushdown. Native support for `$eq`, `$ne`, `$gt/gte/lt/lte`, `$in/$nin`, `$exists`, `$regex` (with `$options="i"`), `$mod`, `$size`, `$type`, `$elemMatch`, `$all`, `$not`, `$and`, `$or`, `$nor`. Only `$where` and `$text` fall back to in-Python evaluation (security + Mongo-specific). Field-path validator `_SAFE_SEGMENT_RE`; all values bound as positional parameters.
- **`PostgresTransaction`**: holds a dedicated pool connection for the duration of a transaction. Wraps asyncpg's native `connection.transaction()`. Supports save / get / delete / find inside the transactional scope.
- **Walker BFS via recursive CTE** (`PostgresDB.traverse`): single SQL statement replaces N round trips. Direction `"out"` / `"in"` / `"both"`, configurable `max_depth`, optional `edge_filter` (Mongo-style, must push down). Returns `{node_id, parent_id, edge_id, depth}` tuples deduplicated by shortest depth.
- **Multi-tenant RLS** (`PostgresDB.enable_rls` + `PostgresDB.tenant`): per-tenant data isolation enforced in the database. `enable_rls(collection)` installs a policy gated on `current_setting('app.tenant_id', true)` (configurable to admit `tenant_id IS NULL` global rows). `tenant(tid)` async context wraps each request in a transaction and sets the GUC via `set_config()`. Uses `contextvars` so sibling async tasks have independent scopes and nested scopes shadow correctly. Tables are forced (`FORCE ROW LEVEL SECURITY`) so RLS applies to the table owner too — production deployments must connect as a non-superuser, non-BYPASSRLS role.
- **pgvector integration** (`PostgresDB.enable_vector_column` + `$near` operator): declare a `vector(N)` column with HNSW (default) or IVFFlat index. Embeddings flow through the normal `save()` / `bulk_save_detailed()` path — the adapter mirrors the field into the dedicated column. New `$near` query operator translates to `ORDER BY <field> <=> $vec LIMIT N` in the same SQL statement as JSONB metadata filters, enabling hybrid KG + metadata + vector queries in one round trip. Configurable distance ops (`vector_cosine_ops` default, `vector_l2_ops`, `vector_ip_ops`). Vector encoding accepts list / tuple of numbers; rejects non-numeric input with `TypeError`.
- **Public re-export**: `from jvspatial.db import PostgresDB`; factory registration as `create_database("postgres", ...)` and `create_database("postgresql", ...)` alias.
- Optional install groups in `pyproject.toml`: `[postgres]` (`asyncpg>=0.29.0`) and `[pgvector]` (`asyncpg>=0.29.0` + `pgvector>=0.2.5`).
- **Test coverage**: 76 unit tests (`tests/db/test_postgres_translate.py`, `tests/db/test_postgres_unit.py`) covering translator operator pushdown, pool auto-tuning, identifier validation, placeholder shifting, vector encoding, tenant contextvar semantics, vector-clause peeling. 25 integration tests (`tests/db/test_postgres_integration.py`) against a live PG 16 + pgvector container, covering CRUD, operator pushdown end-to-end, atomic compound ops, walker traverse (one / two hop, in / out / both, depth metadata), RLS tenant isolation (with dedicated non-superuser test role), pgvector round-trip + ANN ranking + hybrid JSONB+vector queries. Integration tests skip gracefully when no live PG is reachable.
- **Documentation**: `docs/md/postgres-guide.md` (adoption + schema + pool tuning + transactions + bulk writes + env vars), `docs/md/multi-tenant-rls.md` (RLS pattern + critical non-superuser requirement + insertion semantics + testing patterns), `docs/md/vector-store.md` (pgvector + index options + hybrid queries + graph+vector composition), `docs/md/neon-deployment.md` (pooler endpoint + branching for preview environments + scale-to-zero), `docs/md/aurora-serverless-deployment.md` (capacity tuning + RDS Proxy + IAM auth + cost notes).

### Phase A — Strip & hot-path remediation (2026-05-26)

#### Performance

- `Object` per-instance validation overhead reduced significantly. The previously-O(MRO) `_get_class_hierarchy_fields()` is now a per-subclass frozenset cache populated by `AttributeMixin.__pydantic_init_subclass__`. Hot-path measurements on a 10-field `Sample(Node)` subclass:
  - `_get_class_hierarchy_fields()`: **2.03 → 0.28 µs/call** (~7×)
  - `Sample()` instantiation: **15.72 → 8.78 µs/inst** (~1.8×)
  - `obj.name = "y"` assignment: **7.13 → 0.65 µs/set** (~11×, near pure-Pydantic baseline of 0.19 µs)
- `get_protected_attrs` / `get_transient_attrs` now read from per-class `__protected_attrs_cache__` / `__transient_attrs_cache__` frozensets populated at class-definition time. Fall back to MRO walk for classes that did not go through `AttributeMixin`.
- `JsonDB` now uses `orjson` when available (optional fast-path; gracefully falls back to stdlib `json`). Combined with dropping `indent=2` on every write, this delivers ~1.6× speedup on `find(1000)` scans and removes a 37× serialization-cost ratio versus the previous indented stdlib path. JsonDB remains a development-only backend; the perf win is for tight dev-loop iteration.

#### Removed

- **BREAKING (API):** `JsonDBTransaction` class and its `best_effort=True` buffered-commit mode. Rationale: JsonDB is a dev-only backend and the buffered-transaction layer offered weaker-than-ACID guarantees that the audit deemed misleading (writes could be lost on mid-commit crash; not atomic against external readers). Callers needing transactions should use MongoDB and check `Database.supports_transactions`. The base `Transaction` ABC and `MongoDBTransaction` remain unchanged.
- `tests/db/test_transaction_semantics.py` (entirely; covered the removed surface).
- `aiofiles` is no longer a required runtime dependency. JsonDB falls back to `asyncio.to_thread`; the aiofiles import branch was removed. Install footprint shrinks by one dep for every consumer.
- `setuptools_scm[toml]` removed from `[build-system].requires`. The project reads its version from `jvspatial/version.py` via `setup.py`, so setuptools_scm was unused.
- **BREAKING:** Python 3.8 support dropped. `requires-python = ">=3.9"`; the `Programming Language :: Python :: 3.8` classifier is gone; `[tool.black].target-version` no longer lists `py38`. CI did not actually test 3.8 (ROADMAP §2.8); the declaration was aspirational and several internal modules use 3.9+ typing idioms.

#### Changed

- `Node.__init_subclass__` and `Edge.__init_subclass__` now delegate `@on_visit` hook collection to a shared helper `jvspatial.core.entities._visit_hooks.register_visit_hooks(cls, label=…)`. The two implementations were ~50 lines of duplicate logic; both shrunk to ~3 lines apiece. Behavior unchanged.
- `JsonDB._async_write_json` and `_sync_write_record` now emit compact JSON. The `indent=2` pretty-print was a dev affordance whose cost dominated write throughput.

#### Added

- `Object.__hierarchy_fields__: ClassVar[frozenset[str]]` — per-class cached frozenset of valid field names across the MRO. Read by the hot `__setattr__` path.
- `AttributeMixin.__pydantic_init_subclass__` — populates the per-class hot-path caches after Pydantic has finalized `model_fields`.
- `jvspatial.core.entities._visit_hooks` (internal) — shared visit-hook registration helper used by Node and Edge.

### Added

- `JVSPATIAL_DOCS_DISABLED` env var (truthy `1`/`true`/`yes`/`on`) — when set, `AppBuilder.create_app` constructs FastAPI with `docs_url=None`, `redoc_url=None`, `openapi_url=None`, and `swagger_ui_oauth2_redirect_url=None` so the documentation surface is fully unpublished (404 with no spec leak). Recommended for production.
- `Walker.__entity_name__` / `Walker._entity_name()` — parallel to `Object._entity_name()` so walker IDs and the persisted `entity` discriminator honor the per-subclass override. (Audit §1.1, §1.2, §1.9.)
- `TraversalProtection.start_if_needed()` — idempotent initializer for `Walker.run()`. Pause/resume cycles no longer reset step / visit / wall-clock counters. (Audit §2.2.)
- `WalkerTrail(max_length=N)` — wires the previously-undocumented bound. `0` (default) means unlimited; positive integers cap the in-memory trail. Threaded through `Walker(max_trail_length=...)` and `JVSPATIAL_WALKER_MAX_TRAIL_LENGTH`. (Audit §2.3 / SPEC §6.4.)
- `tests/core/test_entity_name_walker_and_save.py`, `tests/core/test_walker_protection_audit_fixes.py`, `tests/storage/test_versioning_path_sanitizer_audit.py`, `tests/api/test_webhook_hmac_audit_fix.py` — 28 new regression cases pinning Wave 1 audit fixes.
- Public `invalidate_api_key_cache(api_key)` and `invalidate_api_key_cache_hash(cache_key)` helpers in `jvspatial.api.integrations.webhooks.webhook_auth`. `APIKeyService.revoke_key` now invokes the latter so revocations are effective immediately rather than after the 5-minute TTL. (Audit §4.5.)
- `tests/db/test_default_compound_ops_id_normalization.py`, `tests/core/test_pager_audit_fixes.py` — 11 new regression cases pinning Wave 2 audit fixes.
- `jvspatial.db.database.BulkSaveResult` dataclass and `Database.bulk_save_detailed()` method. Reports `attempted` / `saved` / `failed_ids` per call so partial-success backends (JsonDB, DynamoDB) can no longer silently drop records. `bulk_save` is preserved as a thin int-returning wrapper for back-compat. (Audit §5.6-§5.7.)
- `MongoDB.is_transactional()` async probe. Uses the `hello` admin command to detect replica-set / sharded topology and caches the result. Use this instead of the static `supports_transactions` flag when the caller intends to actually open a transaction. (Audit §5.9.)
- `CORSConfig.cors_allow_wildcard` opt-out. When `cors_origins` contains a wildcard and this is `False` (default), a startup WARNING is emitted. SPEC §15.4 promised this; the audit found it missing. (Audit §4.12.)
- `JVSPATIAL_STRICT_ENV_ALLOWLIST` env var. Truthy values turn unknown-`JVSPATIAL_*` key detection from a per-key WARNING into a startup `ValueError` so typos fail-fast. (Audit §7.1 / SPEC §10.2.)
- `ALLOWED_ENV_KEYS` frozenset and `enforce_env_allowlist()` / `discover_unknown_jvspatial_env_keys()` helpers in `jvspatial.env_adapter`. Called from `validate_server_config_requirements()` at server startup.
- New top-level / field-level `QueryEngine` operators: `$nor` (top-level logical), `$mod`, `$all`, `$type`, `$not` (field-level). Previously advertised by `QueryBuilder` but silently returned no matches. (Audit §5.2.)
- `tests/api/test_env_allowlist_audit.py`, `tests/api/test_cors_wildcard_and_error_detail_audit.py`, `tests/db/test_query_operator_parity_audit.py`, `tests/db/test_bulk_save_detailed_audit.py` — 22 new regression cases pinning Wave 3 audit fixes.
- `jvspatial.utils.stability.emit_experimental_once(name, message)` — public hook for opt-in surfaces that need to emit the experimental warning without going through the `@experimental` decorator (replaces private `_emit_once` calls). (Audit §7.7.)
- `tests/db/test_sqlite_cross_loop_audit.py`, `tests/utils/test_wave4_polish_audit.py` — 10 new regression cases pinning Wave 4 audit fixes.
- `jvspatial.core.entities.TraversalSkipped` and `TraversalPaused` exception classes. `Walker.skip()` now raises `TraversalSkipped` (caught via `except TraversalSkipped`); previously relied on substring-matching `"Node skipped"` in the message. (Audit §2.9 / SPEC §6.5.)
- `PathSanitizer` rejects Windows-reserved filenames (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`) regardless of host OS. ``CON.txt`` is rejected; ``CONFIG.json`` passes. (Audit §4.18 / SPEC §15.1.)
- `tests/storage/test_windows_reserved_audit.py`, `tests/core/test_wave5_walker_audit.py`, `tests/api/test_deferred_invoke_fail_closed_audit.py`, `tests/db/test_sqlite_id_coercion_audit.py` — 23 new regression cases pinning Wave 5 audit fixes.

### Fixed

- **BREAKING (behavioral):** `Walker.run()` now raises `InfiniteLoopError` / `WalkerTimeoutError` / `WalkerExecutionError` when protection limits trip, as SPEC §6.3 has always promised. Earlier behavior silently swallowed `ProtectionViolation` into `walker.report` and returned. Callers that relied on the swallow contract must wrap `spawn()` / `run()` in `try`/`except`. (Audit §2.1.)
- `GraphContext.save_object` no longer rewrites entity IDs when `__entity_name__` differs from `cls.__name__`. Earlier the ID-validation check compared against `cls.__name__` and regenerated through `cls.__name__` — any entity using the override had its ID silently corrupted on every save. (Audit §1.3, §1.4.)
- `GraphContext.find_edges_between` honors `__entity_name__` so override-using edges are findable. Earlier filtered `entity == edge_class.__name__`. (Audit §1.5.)
- `Node._node_query` keys edge lookups by the persisted `entity` field (not the non-existent `name` column) and honors `__entity_name__`; `Node.count_neighbors` fast-path regex uses `_entity_name()`; `Node._matches_node_filter` compares against `_entity_name()`. (Audit §1.6-§1.8.)
- `AuthenticationService._verify_refresh_token` SHA-256 fallback now uses `hmac.compare_digest` instead of `==`. Removes a timing oracle on refresh-token and password-reset-token hash comparison. (Audit §4.1 / SPEC §15.2.)
- `LocalFileInterface.{create_version, get_version, list_versions, delete_version, get_latest_version}` route `file_path` through a new `_sanitized_version_base` helper. Earlier these computed `self.root_dir / f"{file_path}.versions"` without sanitization — a caller-supplied `../../etc/passwd` escaped the storage root entirely. (Audit §4.2 / SPEC §15.1.)
- `verify_hmac_signature` no longer slices `expected_signature[len(prefix):]`. The earlier slice truncated 7 chars off a 64-char SHA-256 digest so `hmac.compare_digest` always returned False — webhook HMAC verification rejected every request. (Audit §4.3 / SPEC §15.2.)
- Webhook walker `inject_walker_webhook_payload.enhanced_init` is now sync. Python ignores `async def __init__`; the earlier form returned a coroutine that was never awaited and leaked on every webhook walker construction. (Audit §3.1.)
- `webhook_wrapper` now awaits `endpoint_func(**kwargs)` in the async branch. Both arms of the `if/else` were identical, so coroutines from async endpoints leaked unawaited. (Audit §3.2.)
- `FileStorageService.handle_delete_file` now awaits `self.file_interface.delete_file(file_path)`. The missing `await` left `success` as the coroutine object and skipped the delete. (Audit §3.3.)
- `generate_graph_dot` and `generate_graph_mermaid` now wrap `Path.write_text` in `asyncio.to_thread` so disk I/O does not block the event loop inside their async bodies. (Audit §3.4-§3.5.)
- `WalkerQueue.prepend` / `append` / `add_next` / `insert_after` / `insert_before` now respect `max_size` and emit a one-shot WARNING on first drop. Earlier the front-of-queue and middle-insert paths bypassed the cap, providing a silent protection bypass. (Audit §2.4-§2.5.)
- `DynamoDB.{find, count, batch_get, batch_write}` now route every `aioboto3` wire call through `_run_with_throttle_retry`. Earlier the helper was only applied to `save`/`get`/`delete`; `ProvisionedThroughputExceededException` and `ThrottlingException` from scan / query / batch ops surfaced to callers as immediate failures despite the documented backoff. (Audit §5.1 / SPEC §4.3.)
- Security headers middleware now emits a relaxed Content-Security-Policy on `/docs`, `/redoc`, `/openapi.json` (and sub-paths) that permits `cdn.jsdelivr.net` so FastAPI's bundled Swagger UI / ReDoc pages render. The previous strict default blocked the CDN-hosted JS/CSS and the docs loaded blank. Application routes keep the strict default policy.
- **BREAKING (behavioral):** `ObjectPager.get_page` no longer returns cached results. The in-memory `_cache` attribute is removed entirely; every call hits the database. Stale-after-write semantics are eliminated. Callers that relied on caching should use the backend-level read-through cache via `create_database(cache_get_size=...)`. (Audit §8.2.)
- `ObjectPager.get_page(after_id=..., order_by=...)` now raises `ValueError`. Keyset pagination via `after_id` only tracks `id`; combining it with a custom sort key silently skipped or duplicated rows on writes between pages. Use offset pagination if you need a custom sort. (Audit §8.1.)
- Default `Database.find_one_and_update` and `Database.find_one_and_delete` now normalize `{"_id": x}` queries to `{"id": x}` when only `_id` is present, so Mongo-style queries no longer silent-miss on JsonDB / SQLite / DynamoDB (which persist records keyed by `id` only). MongoDB native override is unaffected. (Audit §5.3 / SPEC §4.1.)
- JsonDB no longer blocks the event loop. Every `Path.exists()` / `Path.glob()` call inside `async` methods (`_async_read_json`, `count`, `find_many`, `find`) is now wrapped in `asyncio.to_thread`. (Audit §3.6 / SPEC §3.3.)
- `Node.__init_subclass__`, `Edge.__init_subclass__`, and `Walker.__init_subclass__` now call `super().__init_subclass__(**kwargs)` so `AttributeMixin.__init_subclass__` runs and `protected` / `transient` / `private` attribute registration completes for their subclasses. (Audit §6.1-§6.3 / SPEC §2.5.)
- `SessionManager` mutations now hold an `asyncio.Lock` so concurrent create/invalidate/cleanup cannot raise `RuntimeError: dictionary changed size during iteration`. `max_sessions_per_user` enforcement is no longer racy — over-cap creation evicts the oldest session by `last_accessed`. (Audit §4.8.)
- `_API_KEY_CACHE` (webhook layer) now holds a lock around reads, eviction, and miss-population. Removes a `KeyError` window when a size-cap cleanup races a reader. (Audit §4.7.)
- `APIKeyService(context=None)` now defaults to the **prime** database instead of `get_default_context()`. Auth state is required to live on the prime DB (SPEC §9 / CLAUDE.md §1). (Audit §4.4.)
- `APIKeyService.revoke_key` now invokes the new webhook cache-invalidation hook so a revoked key stops authenticating immediately rather than after the 5-minute TTL. (Audit §4.5.)
- `JVSPATIAL_EXPOSE_ERROR_DETAILS=true` is now ignored when the runtime is signalled as production (`JVSPATIAL_ENVIRONMENT` or `ENVIRONMENT` set to `prod`/`production`). Emits a once-per-process WARNING explaining the suppression. Generic 500 message is returned. (Audit §4.10 / SPEC §15.5.)
- `MongoDB.begin_transaction` now short-circuits to `None` on standalone deployments instead of attempting `start_session` / `start_transaction` every call. Topology is probed once via `is_transactional()` and cached. (Audit §5.9 / SPEC §4.2.)
- `QueryEngine.match` and `QueryEngine._match_value` now raise `QueryError` on unsupported operators rather than silently returning False. Optimizer markers (`$hint`, `$select`) injected into queries are skipped explicitly instead of treated as unknown operators. (Audit §5.2 / SPEC §5.1.)
- Bool parsing consolidated across `jvspatial.env`, `jvspatial.env_adapter`, `jvspatial.runtime.serverless`, and `jvspatial.api.components.app_builder`. All three of the latter delegate to `env.parse_bool`. `JVSPATIAL_DEBUG=on` and `SERVERLESS_MODE=on` now agree on truthiness. (Audit §7.2-§7.3.)
- Unknown `JVSPATIAL_*` env keys now warn at startup (or raise in strict mode). Closes a SPEC §10.2 gap that allowed typos to silently no-op. (Audit §7.1.)
- `SQLiteDB` instances now silently rebind their `aiosqlite` connection when reused across event loops for file-backed paths. The previous opaque "Future attached to a different loop" error from inside `aiosqlite` is replaced with transparent recovery. `:memory:` databases keep the existing connection (rebinding would silently truncate the dataset). (Audit §5.10 / SPEC §4.3.)
- Security headers middleware derives the CSP-relaxation prefixes from `ServerConfig.docs_url` / `redoc_url` / `openapi_url` at install time. Callers customizing the docs URL (e.g. `docs_url=/api/docs`) keep Swagger UI rendering under the relaxed CSP. (Audit §7.13.)
- JWT debug log no longer includes the secret length (narrowing a brute-force search space). Logs `secret_configured=bool(...)` instead. (Audit §4.11 / SPEC §15.5.)
- `validate_token` warning logs `db_type=` instead of `db_path=` so the on-disk filesystem layout does not leak to log sinks. (Audit §4.13 / SPEC §15.5.)
- `LoggingNoopTaskScheduler.schedule` downgraded from per-call WARNING to DEBUG so misconfigured serverless deployments do not flood CloudWatch — the once-per-process startup error from `serverless.factory._note_noop_in_serverless` is sufficient. (Audit §7.14.)
- **BREAKING (behavioral):** the internal deferred-invoke route fails closed when `JVSPATIAL_DEFERRED_INVOKE_SECRET` is unset. Previous "no secret = allow everything" semantics exposed the endpoint to any caller on misconfigured deployments. Set the secret to enable the route, or set `JVSPATIAL_DEFERRED_INVOKE_DISABLED=true` to skip registering it entirely. (Audit §4.16 / SPEC §15.2.)
- **BREAKING (behavioral):** `Walker(type_code=...)` raises `ValueError` when given a value other than `"w"`. The SPEC §1.1 ID-format invariant (`w.EntityName.<hex>`) cannot be corrupted by a stray kwarg. (Audit §2.10.)
- Walker `skip()` raises `TraversalSkipped` rather than `JVSpatialError("Node skipped")`. Callers that catch the generic exception or match on the substring will need to update — `except TraversalSkipped:` is the new contract. (Audit §2.9.)
- `SQLiteDB.save` coerces `record["id"]` to `str` so int / `uuid.UUID` ids round-trip correctly through SQLite's TEXT column. The persisted record now also stores the stringified id. (Audit §5.20.)
- `runtime/serverless._parse_bool` logs a WARNING on unrecognized `SERVERLESS_MODE` values (still maps to False for back-compat). Silent garbage-to-False mapping hid typos. (Audit §7.3.)
- `.env.example` CORS section corrected: `Default: *` and `JVSPATIAL_CORS_ORIGINS=*` example replaced with the actual default localhost whitelist, plus a note that wildcards trigger a startup WARNING. (Audit §7.5.)
- `JsonDB._list_collection_json_files` drops the dead `not p.name.endswith('.jvtmp')` filter; tmp files are named `<id>.json.<pid>.<hex>.jvtmp` and never match the `*.json` glob. (Audit §5.16.)

### Deprecated

- `jvspatial.core.utils.generate_id_async` — deprecated alias for `generate_id`. ID generation is pure computation (SPEC §3.2); the async signature was a vestige. Scheduled for removal in 0.1.0. (Audit §3.11.)

### Removed

- `jvspatial.db.transaction.JSONTransaction` — unused dead code superseded by `JsonDBTransaction`. (Audit §5.14.)

## [0.0.7] - 2026-05-08

### Security

- **BREAKING**: JWT secret must be set explicitly when authentication is enabled. The server now fails fast with a clear error if `JVSPATIAL_JWT_SECRET_KEY` is not set or uses a placeholder value. Set via environment or `Server(auth=dict(jwt_secret="..."))`.
- Add security headers middleware (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection) applied to all responses by default. Configurable via `Server(security=dict(security_headers_enabled=True))`.
- AuthConfig `jwt_secret` default changed from `"your-secret-key"` to empty string; explicit setting required when auth is enabled.
- Remove duplicate `/auth/register` from auth exempt paths.
- Add weekly `pip-audit` workflow (`.github/workflows/security.yml`).

### Added

- **IO durability:** `JsonDB` writes now go through an atomic `temp + fsync + rename + fsync(dir)` helper (`jvspatial/db/_atomic.py`); a process crash, kernel panic, or power loss can never leave a partial record on disk. Orphan `*.jvtmp` files left by prior crashed processes are reaped on startup (skipped under serverless mode).
- **Per-path locking:** `JsonDB` uses a bounded-LRU `PathLockManager` (`jvspatial/db/_path_locks.py`) so concurrent writes to different files run in parallel while same-file writes serialize. Cross-thread safe.
- **Atomic version metadata** in `LocalFileInterface.create_version()` and `save_file()` via the same helper.
- **Native `Database.count()`** with filter pushdown across all backends. SQLite gains a Mongo→SQL query translator (`jvspatial/db/_sqlite_translate.py`) that pushes `$eq`/`$ne`/`$gt`/`$gte`/`$lt`/`$lte`/`$in`/`$nin`/`$exists`, top-level AND, and `$and`/`$or` (recursive) into `WHERE … json_extract()` clauses with `LIMIT`/`ORDER BY` pushdown. MongoDB gains native `count_documents`/`estimated_document_count`. DynamoDB gains `Select="COUNT"`. JsonDB gains a dirent-only fast path for empty queries.
- **Bulk APIs:** `Database.find_many(ids)` and `Database.bulk_save(records)` with native overrides on every backend (Mongo `$in` + `bulk_write`, SQLite single-transaction `IN`/`executemany`, DynamoDB `BatchGetItem`/`BatchWriteItem`, JsonDB parallel reads/writes).
- **Capability flags:** `Database.supports_transactions` (False default; True on MongoDB) so callers can branch without sniffing adapter classes.
- **Read-through cache wrapper:** opt-in via `create_database(cache_get_size=N, cache_get_ttl=S)`. LRU + TTL, invalidates on save/delete, refreshes on `bulk_save`/`find_one_and_update`, skipped under serverless.
- **Observability layer:** opt-in via `create_database(observe=True, slow_query_ms=N, metrics=...)`. Emits a structured log line per DB op (`backend`/`op`/`collection`/`duration_ms`/`success`/`result_count`) with WARNING-elevation at the slow-query threshold, plus four metrics (`jvspatial.db.op.duration_seconds`, `.count`, `.slow_count`, `.result_count`).
- **`MetricsRecorder` Protocol** with `NullMetricsRecorder` default. Optional **OpenTelemetry adapter** under `pip install jvspatial[otel]` (`jvspatial/observability/otel.py`).
- **Shared retry helper** (`jvspatial/utils/retry.py`): async `retry_async()` and `@retry()` decorator with exponential backoff + full jitter, configurable retryable predicate, optional `on_retry` hook. Used by MongoDB connection-error recovery, DynamoDB throttle errors, S3 SlowDown/5xx errors.
- **S3 multipart uploads** at ≥ 8 MiB (configurable via constructor or `JVSPATIAL_S3_MULTIPART_THRESHOLD` env). Uses boto3's `TransferManager` for splitting, parallel parts, and resume-on-failure.
- **DynamoDB throttle retry:** `save`/`get`/`delete` auto-retry on `ProvisionedThroughputExceededException`, `ThrottlingException`, `RequestLimitExceeded`, `TooManyRequestsException`, `TransactionConflictException`.
- **DeferredSave auto-flush:** new `max_pending_saves` class attr (default `None`/disabled) bounds in-memory dirty state for callers who forget to flush.
- **`@experimental` and `@deprecated` decorators** (`jvspatial/utils/{stability,deprecation}.py`) with once-per-process warnings, async support, serverless suppression. `JsonDBTransaction(best_effort=True)` is now wired to emit the experimental warning.
- **PEP 561 typing:** `jvspatial/py.typed` marker shipped via `pyproject.toml` package data so mypy/pyright treat jvspatial as typed.
- **Benchmark suite:** `tests/benchmarks/` with 13 benches across JsonDB / SQLite / DeferredSave guarding the new IO wins. New `.github/workflows/benchmarks.yml` posts a regression-comparison comment on every PR (vs. the latest `bench-baseline` artifact published from `main`).
- **Community-readiness scaffolding:** `CONTRIBUTING.md` (root), `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1 by reference), `RELEASING.md` aligned with the `version.py`-driven publish workflow.
- **Stability contract:** `docs/md/stability.md` declaring public/internal/experimental tiers and the deprecation policy.
- **Observability + benchmarks docs:** `docs/md/observability.md`, `docs/md/benchmarks.md`.
- **Dependabot:** `.github/dependabot.yml` for `pip` and `github-actions` ecosystems, weekly with grouped minor/patch bumps.
- `Database.drop_deprecated_indexes()` optional hook (default no-op) for named-index cleanup; MongoDB implementation drops listed names. Documented in [Custom Database guide](docs/md/custom-database-guide.md) and [optimization](docs/md/optimization.md#declarative-database-indexing) (index creation timing, partial indexes, MongoDB conflict handling).
- `SecurityConfig` with `security_headers_enabled` option.
- [Production Deployment Guide](docs/md/production-deployment.md) with security checklist.

### Changed

- **BREAKING (limited):** `JsonDBTransaction(db).save/get/delete/find()` now raises `NotImplementedError` by default instead of silently no-op'ing. Pass `best_effort=True` to opt into the buffered-commit semantics, or check `Database.supports_transactions` and fall back to non-transactional writes. Audited downstream consumers (`jvagent`, `integral`) — neither uses this surface, so no coordinated change required.
- **`QueryEngine` optimization cache** is now bounded by an LRU (default 1024 entries, configurable via `QueryEngine(cache_size=...)`). Was unbounded.
- **MongoDB retries** now go through the shared retry helper (`utils/retry.py`); behavior preserved (one retry on connection-error with reset).
- CI coverage gate raised from 55 → 60% to reflect the new tested code.
- Security headers are applied automatically (enabled by default).
- `pyproject.toml` adds `[otel]` extra and a `benchmark` pytest marker; default `pytest` invocation now skips `tests/benchmarks/` (run with `pytest tests/benchmarks --benchmark-only`).

## [0.0.5] - Previous

See git history for changes before this release.
