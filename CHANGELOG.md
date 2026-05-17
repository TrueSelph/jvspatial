# Changelog

All notable changes to jvspatial will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
