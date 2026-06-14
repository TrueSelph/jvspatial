# jvspatial/db

Database abstraction and backends — JSON, SQLite, MongoDB, DynamoDB. Plus query engine, transactions, atomic IO, path locks, cache wrapper, and observability wrapper.

> **Read first**: [SPEC §4-5](../../SPEC.md), [docs/md/mongodb-query-interface.md](../../docs/md/mongodb-query-interface.md)

---

## Purpose

`db/` defines the `Database` ABC and ships four production backends, all sharing a Mongo-style query DSL. Internal wrappers (`_cache`, `_observable`) add cross-cutting concerns to any backend through factory flags.

## Layout

```
db/
├── database.py            # Database ABC + finalize_find_results
├── factory.py             # create_database, register_database_type, switch_database
├── manager.py             # DatabaseManager + prime DB convention
├── query.py               # QueryEngine + Mongo-style operators
├── transaction.py         # Transaction context + MongoDBTransaction
├── jsondb.py              # JSON file-per-record backend
├── sqlite.py              # aiosqlite backend + Mongo→SQL translator
├── mongodb.py             # motor backend
├── dynamodb.py            # aioboto3 backend
├── _atomic.py             # internal: crash-safe write helper
├── _path_locks.py         # internal: bounded-LRU per-path locks
├── _cache.py              # internal: read-through cache wrapper
├── _observable.py         # internal: structured log + metrics wrapper
└── _sqlite_translate.py   # internal: Mongo → SQL translator
```

## Backend matrix

| Backend | Transactions | Bulk APIs | Native count | Notes |
|---|---|---|---|---|
| JSON | No (best-effort opt-in only) | Parallel reads/writes | Dirent fast path | Atomic writes, per-file locks |
| SQLite | No (single-conn fsync) | `executemany` + `IN` | Mongo→SQL pushdown | Translator covers `$eq/$ne/$gt/$gte/$lt/$lte/$in/$nin/$exists`, AND, `$and/$or` |
| MongoDB | **Yes** (replica set required) | `bulk_write`, `$in` | `count_documents` / `estimated_document_count` | Native compound ops; shared retry helper |
| DynamoDB | No | `BatchGetItem`/`BatchWriteItem` (100/batch) | `Select="COUNT"` | Throttle retry with backoff |

## Public API (from `jvspatial.db`)

| Name | What it does |
|---|---|
| `Database` | ABC every adapter implements (SPEC §4.1) |
| `create_database(type, ...)` | Factory entry point |
| `create_default_database()` | Environment-driven default |
| `register_database_type(name, factory)` | Register a custom adapter |
| `unregister_database`, `unregister_database_type` | Cleanup |
| `list_database_types()` | Inventory |
| `get_prime_database`, `get_current_database`, `switch_database` | Multi-DB lookup |
| `DatabaseManager`, `get_database_manager`, `set_database_manager` | Manager surface |
| `DatabaseError`, `VersionConflictError` | DB-specific exceptions |
| `JsonDB`, `SQLiteDB`, `MongoDB`, `DynamoDB` | Concrete adapters (optional extras for non-JSON) |

## Invariants

- **`Database.supports_transactions` is a capability flag.** Branch on it; do not sniff adapter class. (`database.py:84`)
- **`find_many` and `bulk_save` are public and benefit from native overrides.** Defaults exist but are slow. (`database.py:176+`)
- **`find_one_and_update` / `find_one_and_delete` are NOT atomic by default.** Only MongoDB overrides with native atomic versions.
- **Atomic JSON writes use `temp + fsync + rename + fsync(dir)`.** No partial records survive a crash. (`_atomic.py`)
- **Per-file locks serialize concurrent writes to the same record only.** Different files run in parallel. (`_path_locks.py`)
- **`QueryEngine` LRU is bounded.** Default 1024; configurable. Unbounded query construction will not leak memory. (`query.py`)
- **Prime database is unique.** Auth state, sessions, API keys live there. Cannot be switched.

## Modification patterns

- **Adding a custom backend**: subclass `Database`, implement abstract methods, override `find_many` / `bulk_save` if you can, set `supports_transactions`, register via `register_database_type`. Add tests under `tests/db/`.
- **Adding a query operator**: extend `QueryEngine.evaluate_*`. If pushdown is feasible, update `SQLiteTranslator` and the DynamoDB query path.
- **Adding a backend capability flag**: declare as class attribute on `Database`, default to `False` (or the safe value). Document in SPEC §4.2.
- **Touching internal wrappers** (`_atomic.py`, `_path_locks.py`, `_cache.py`, `_observable.py`): they are not part of the public API but **the observability log-field schema IS public** (see [docs/md/stability.md](../../docs/md/stability.md)).

## Related docs

- [docs/md/mongodb-query-interface.md](../../docs/md/mongodb-query-interface.md)
- [docs/md/custom-database-guide.md](../../docs/md/custom-database-guide.md)
- [docs/md/dynamodb-guide.md](../../docs/md/dynamodb-guide.md)
- [docs/md/graph-context.md](../../docs/md/graph-context.md)
- [docs/md/caching.md](../../docs/md/caching.md)
- [docs/md/observability.md](../../docs/md/observability.md)
- [docs/md/optimization.md](../../docs/md/optimization.md)
- [docs/md/benchmarks.md](../../docs/md/benchmarks.md)

## Stability

Public surface (above) is stable. Underscore-prefixed modules are internal. The structured log field set from `ObservableDatabase` is part of the public contract — schema changes require a deprecation cycle.
