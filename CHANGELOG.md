# Changelog

All notable changes to jvspatial will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `JVSPATIAL_DOCS_DISABLED` env var (truthy `1`/`true`/`yes`/`on`) — when set, `AppBuilder.create_app` constructs FastAPI with `docs_url=None`, `redoc_url=None`, `openapi_url=None`, and `swagger_ui_oauth2_redirect_url=None` so the documentation surface is fully unpublished (404 with no spec leak). Recommended for production.

### Fixed

- Security headers middleware now emits a relaxed Content-Security-Policy on `/docs`, `/redoc`, `/openapi.json` (and sub-paths) that permits `cdn.jsdelivr.net` so FastAPI's bundled Swagger UI / ReDoc pages render. The previous strict default blocked the CDN-hosted JS/CSS and the docs loaded blank. Application routes keep the strict default policy.

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
