# jvspatial/logging

Structured console logging, persistent database logging, custom log levels.

> **Read first**: [docs/md/logging-service.md](../../docs/md/logging-service.md), [docs/md/custom-log-levels.md](../../docs/md/custom-log-levels.md)

---

## Purpose

`logging/` covers two surfaces:

1. **Structured console logging** — `JVSpatialLogger`, optionally backed by `structlog`. Falls back to stdlib `logging` if `structlog` is not installed.
2. **Database logging service** — `BaseLoggingService` persists log records to a backing database via `DBLogHandler`. Useful for audit trails and post-hoc query.

Custom log levels (`AUDIT`, `SECURITY`, etc.) are supported and integrate with both surfaces.

## Layout

```
logging/
├── __init__.py            # Public surface (this file documents)
├── config.py              # Initialization helpers
├── service.py             # BaseLoggingService
├── handler.py             # DBLogHandler, install_db_log_handler, exception hook
├── models.py              # DBLog entity
├── custom_levels.py       # add_custom_log_level, CUSTOM_LEVEL_NUMBER
└── endpoints.py           # /logs API endpoints (admin)
```

## Public API (from `jvspatial.logging`)

### Database logging

| Name | What it does |
|---|---|
| `BaseLoggingService` | Service that persists log records |
| `get_logging_service()` | Singleton accessor |
| `DBLog` | Pydantic model for persisted records |
| `get_logging_config`, `initialize_logging_database` | Initialization helpers |
| `DBLogHandler`, `install_db_log_handler`, `install_exception_hook` | Wiring |

### Custom log levels

| Name | What it does |
|---|---|
| `add_custom_log_level(name, level_number)` | Register a custom level |
| `get_custom_levels()` | Inventory |
| `is_custom_level(name)` | Predicate |
| `CUSTOM_LEVEL_NUMBER` | Default integer for ad-hoc custom level |

### Structured console logging

| Name | What it does |
|---|---|
| `JVSpatialLogger` | Logger with optional structlog backing |
| `StructuredLoggingConfig` | JSON / coloring configuration |
| `PerformanceLogger` | Convenience for op duration logging |
| `SecurityLogger` | Convenience for auth / rate-limit / brute-force events |
| `get_logger(name)` | Factory |
| `configure_logging(...)` | Configure structlog (JSON / colors) |
| `configure_standard_logging(...)` | Configure stdlib handler (level / colors / preserved handlers) |
| `performance_logger`, `security_logger` | Module-global instances |

## Invariants

- **Custom levels are global state.** Registering twice is idempotent; registering with a conflicting number is rejected.
- **`SecurityLogger` events feed downstream auth analysis.** Auth attempts, rate-limit hits, and brute-force detections must call into `SecurityLogger` or the equivalent, not silently log elsewhere.
- **`DBLogHandler` persists asynchronously.** Synchronous failures (DB down) must not block the request handler — they downgrade to local logging.
- **`structlog` is optional.** Code must not assume it; use the fallback path when `STRUCTLOG_AVAILABLE` is `False`.
- **Secrets must never reach the log pipeline.** Sanitize before logging — see the 500-response sanitizer pattern.

## Modification patterns

- **Adding a custom log level**: call `add_custom_log_level("FOO", 25)` once at startup. Reuse by `logger.log(25, ...)` or extend `JVSpatialLogger`.
- **Persisting a new event type**: extend `DBLog` model or add a sibling model. Update the handler wiring in `handler.py`.
- **Adding a security-relevant log call**: prefer `SecurityLogger` over ad-hoc info logging. Helps downstream audit tooling find events consistently.

## Related docs

- [docs/md/logging-service.md](../../docs/md/logging-service.md)
- [docs/md/custom-log-levels.md](../../docs/md/custom-log-levels.md)
- [docs/md/security-operational-notes.md](../../docs/md/security-operational-notes.md)

## Stability

All names in the public API tables above are stable. `endpoints.py` (admin `/logs` routes) is wired via the API layer and follows the same stability tier as the rest of `jvspatial/api`.
