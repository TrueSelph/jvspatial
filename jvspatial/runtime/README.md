# jvspatial/runtime

Runtime capability detection — primarily serverless mode and Lambda Web Adapter glue.

> **Read first**: [SPEC §11](../../SPEC.md), [docs/md/serverless-mode.md](../../docs/md/serverless-mode.md)

---

## Purpose

`runtime/` answers questions about the deployment environment: "are we in a serverless runtime?", "which provider?", "are we behind Lambda Web Adapter?". Detection results inform mode-dependent defaults (deferred saves, index creation, bcrypt cost) without leaking environment-checking code throughout the library.

## Layout

```
runtime/
├── serverless.py    # is_serverless_mode, detect_serverless_provider, cache reset
├── lwa.py           # internal: Lambda Web Adapter glue
└── eventbridge.py   # internal: EventBridge wiring helpers
```

## Public API (from `jvspatial.runtime`)

| Name | What it does |
|---|---|
| `is_serverless_mode(config=None)` | Effective mode using precedence (SPEC §11.1) |
| `reset_serverless_mode_cache()` | Clear memoization (tests only) |

From `jvspatial.runtime.serverless` (re-exported through `jvspatial`):

| Name | What it does |
|---|---|
| `detect_serverless_provider()` | Returns one of `"aws"`, `"azure"`, `"gcp"`, `"vercel"`, `"unknown"` |

## Invariants

- **Detection precedence is fixed**: explicit `config.serverless_mode` → `get_current_server().config.serverless_mode` → `SERVERLESS_MODE` env → auto-detect from platform env vars. Do not bypass with custom env reads.
- **Auto-detection is memoized via `lru_cache`.** Tests must call `reset_serverless_mode_cache()` between cases that toggle env.
- **Provider detection is best-effort.** Falls back to `"unknown"`; do not rely on provider-specific behavior outside of well-known providers.
- **`SERVERLESS_MODE` env values**: `true`, `1`, `yes`, `enabled` (case-insensitive) → True. Everything else → False.

## Modification patterns

- **Adding a new serverless provider**: extend `_detect_serverless_mode` and `_detect_serverless_provider` with the relevant env var checks. Add a `ServerlessProvider` literal entry. Update tests in `tests/runtime/`.
- **Adding a new mode-dependent default**: read `is_serverless_mode()` at the point of decision, not at import time. Make the default explicit in the relevant SPEC table (§11.2).

## Related docs

- [docs/md/serverless-mode.md](../../docs/md/serverless-mode.md)
- [docs/md/production-deployment.md](../../docs/md/production-deployment.md)

## Stability

`is_serverless_mode`, `reset_serverless_mode_cache`, and `detect_serverless_provider` are stable. `lwa.py` and `eventbridge.py` are internal — go through the public serverless helpers in `jvspatial.serverless`.
