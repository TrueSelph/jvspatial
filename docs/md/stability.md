# API Stability

This document declares which jvspatial APIs are part of the supported
public surface and which are internal or experimental. The contract
governs backwards-compatibility expectations and what callers can
safely depend on.

## Tiers

### Public (stable)

Modules and names listed here follow [Semantic
Versioning](https://semver.org/). Breaking changes require a major
bump (post-1.0) or a minor bump (pre-1.0) and must be called out in
[CHANGELOG.md](../../CHANGELOG.md) under `**BREAKING**`.

These names are exported from `jvspatial/__init__.py`'s `__all__` and
are the canonical import path:

- **Core entities.** `Object`, `Node`, `Edge`, `Walker`, `Root`,
  `GraphContext`.
- **Decorators.** `attribute`, `endpoint`.
- **Server / config.** `Server`, `ServerConfig`.
- **Database.** `Database`, `create_database`. The
  `Database.supports_transactions` capability flag is part of this
  surface, as are the bulk methods `Database.find_many` and
  `Database.bulk_save`. Adapters not overriding the bulk methods
  fall through to the (slower) default serial implementations.
- **Cache.** `create_cache`.
- **Mixins.** `DeferredSaveMixin`, `deferred_saves_globally_allowed`,
  `flush_deferred_entities`.
- **Work-claim helpers.** `claim_record`, `release_claim`,
  `delete_claimed_record`.
- **Serverless.** `is_serverless_mode`, `detect_serverless_provider`,
  `get_task_scheduler`, `dispatch_deferred_task`,
  `register_deferred_invoke_handler`, `dispatch_deferred_invoke`,
  `normalize_deferred_envelope`.
- **Background tasks.** `create_task`, `TaskScheduler`, `RetryConfig`.
- **Serialization helpers.** `serialize_datetime`,
  `deserialize_datetime`.
- **Observability.** `MetricsRecorder` Protocol and
  `NullMetricsRecorder`. `OpenTelemetryMetricsRecorder` from
  ``jvspatial.observability.otel`` (under the ``[otel]`` extra). The
  structured log fields emitted by ``ObservableDatabase`` (the
  ``backend`` / ``op`` / ``collection`` / ``duration_ms`` /
  ``success`` / ``result_count`` schema) are part of the public
  contract too -- breaking changes to the field set need a deprecation
  cycle.

If you import a name from a submodule rather than from `jvspatial`
directly, the import path itself is **not** part of the public
contract. Modules can move; the top-level export name is what we
keep stable.

### Internal (no contract)

Anything whose module path begins with an underscore, or whose
module is documented as internal here, is **not** part of the public
surface. Callers should not import these directly. They can change
or disappear in any release without notice.

Currently internal:

- `jvspatial.db._atomic` — crash-safe write helpers.
- `jvspatial.db._path_locks` — per-path lock manager.
- `jvspatial.db._sqlite_translate` — Mongo→SQLite query translator.
- `jvspatial.db._cache` — read-through cache wrapper. Use via
  ``create_database(cache_get_size=...)``, not by importing
  ``CachingDatabase`` directly.
- `jvspatial.db._observable` — observability wrapper. Use via
  ``create_database(observe=True)``, not by importing
  ``ObservableDatabase`` directly.
- `jvspatial.api.server_app_factory`, `server_registration`,
  `server_lifecycle`, `server_run`, `server_configurator` — Server
  internals; assemble through `Server` only.
- `jvspatial.runtime.lwa`, `eventbridge` — runtime adapter glue;
  use the public serverless helpers above.
- Any name beginning with `_` in any module.

### Experimental (opt-in, may change)

APIs marked with `@experimental` (see
`jvspatial.utils.stability.experimental`) are public enough to use
but may change or be removed in any minor release. Callers who use
them accept that contract. Each call site emits a warning the first
time the API is used in a given process; the warning can be silenced
per-API or globally.

Currently experimental:

- `JsonDBTransaction(best_effort=True)` — buffered transaction mode.
  See the `JsonDBTransaction` docstring.

(Decorator usage and silencing examples are in
[`docs/md/decorator-reference.md`](decorator-reference.md) — once the
first experimental API is wrapped, that page links here.)

## Deprecation policy

When a public API is going to be removed:

1. The next minor release marks it deprecated with the
   `@deprecated` decorator from `jvspatial.utils.deprecation`, which
   emits a once-per-process `DeprecationWarning` pointing at the
   replacement and the target removal version. The change also lands
   in `CHANGELOG.md`.
2. The deprecation is documented in this file under a new
   `## Deprecated` section with the deprecation version and the
   target removal version.
3. Removal happens at the earliest in the **second** minor release
   after the deprecation is introduced (i.e. one full minor cycle of
   warnings).

We don't promise to follow this policy strictly pre-1.0 — minor
versions can break things — but we still try to give one cycle of
warnings whenever it's reasonable.

Example:

```python
from jvspatial.utils.deprecation import deprecated

@deprecated(
    replacement="Database.find_many()",
    remove_in="0.X+1",
    note="See docs/md/stability.md#deprecation-policy",
)
async def old_bulk_get(...):
    ...
```

## What "internal" means in practice

If you find yourself reaching for an internal helper, please open
an issue describing the use case rather than importing it. Either:

- the use case justifies promoting the helper to public, in which
  case we'll do that in the next minor; or
- there's an existing public API that does the same thing better,
  and we'll point you at it.

Either way, the result is a more stable foundation for everyone.
