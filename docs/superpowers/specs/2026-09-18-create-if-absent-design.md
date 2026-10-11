# Design: `Object.create_if_absent` / `Database.insert_if_absent`

**Date:** 2026-09-18
**Status:** Proposed
**Target version:** 0.0.20 (minor, pre-1.0)
**Motivation:** Durable idempotency records need atomic create-or-return-existing semantics. Today every `Database.save` path is upsert (`INSERT OR REPLACE` / `ON CONFLICT DO UPDATE` / Mongo `replace_one(upsert=True)`), so concurrent writers can overwrite peers and SQLite unique collisions can delete the wrong row via `OR REPLACE`.

## Goal

Ship a portable, atomic **insert-if-absent** primitive:

1. Persist a new record only when no conflict exists on the target key.
2. Never update or replace an existing row.
3. Return the **stored** winner plus a boolean `created` flag.
4. Work identically (semantic contract) across SQLite, Postgres, MongoDB, JsonDB, and DynamoDB.

Integral Core will use this for `QueryResultSet` and similar receipt/idempotency Objects after jvspatial ships.

## Non-goals

- Changing `save()` / `create()` upsert semantics.
- Business-key `ON CONFLICT` on arbitrary unique indexes in v1 (phase 2).
- Automatic migration of webhook `get_or_create_idempotency_key` (follow-up once unique index exists).
- Cross-document multi-key transactions on backends without transactions.

## Public contract

### `InsertIfAbsentResult`

```python
@dataclass(frozen=True)
class InsertIfAbsentResult:
    record: Dict[str, Any]  # stored document (existing or newly inserted)
    created: bool
```

### `Database.insert_if_absent`

```python
async def insert_if_absent(
    self,
    collection: str,
    data: Dict[str, Any],
    *,
    conflict_target: str = "id",
) -> InsertIfAbsentResult:
    ...
```

**v1 rules:**

- `conflict_target` must be `"id"` (primary key). Other values → `ValueError`.
- Missing / empty `id` in `data` → `ValueError` (same as existing Postgres payload split).
- On insert success: `created=True`, return the inserted record (normalized as other writes).
- On conflict: `created=False`, **load and return the existing stored record unchanged** (no merge of proposed fields).
- Must not call through `save()`.

### `Object.create_if_absent`

```python
@classmethod
async def create_if_absent(cls, **kwargs) -> tuple["Object", bool]:
    """Create and persist only if absent.

    Idempotent when the caller supplies a deterministic ``id``.
    Unlike ``create()`` / ``save()``, never updates an existing row.
    """
```

**Flow:**

1. `obj = cls(**kwargs)` (auto-id if omitted — same as `create`).
2. `await context.ensure_indexes(cls)`.
3. Export record; `await database.insert_if_absent(collection, record)`.
4. If `created=False`, rehydrate entity from stored record (not the proposed in-memory instance).
5. Attach `_graph_context`; update entity cache consistently with `save`.
6. If `DeferredSaveMixin` and `created`, `await flush()` (mirror `create()`).
7. Return `(entity, created)`.

Optional kwargs **not** in v1: `raise_on_conflict`. Callers inspect `created`.

## Adapter semantics

| Backend | Insert path | Conflict path |
|---------|-------------|---------------|
| **Postgres** | `INSERT ... ON CONFLICT (id) DO NOTHING RETURNING data`; if no row returned, `SELECT` by id | Return stored row, `created=False` |
| **SQLite** | `INSERT OR IGNORE INTO records ...`; if `changes()==0`, `SELECT` | **Never** `INSERT OR REPLACE` |
| **MongoDB** | `insert_one`; catch `DuplicateKeyError` → `find_one` | Return stored doc |
| **JsonDB** | Under path lock: if file exists → read; else write | Same-id atomic via lock; no secondary unique enforcement |
| **DynamoDB** | `PutItem` with `attribute_not_exists(id)` | Conditional check fail → `GetItem` |

Wrappers (`CachingDatabase`, `ObservableDatabase`) must override or forward `insert_if_absent` so cache/metrics stay correct on both created and existing paths.

Default ABC implementation: raise `NotImplementedError` with a clear message, **or** a documented non-atomic find-then-insert only if PRD requires a default — prefer requiring every built-in adapter to implement (PRD §8).

## Error handling

- `ValueError` — missing id, unsupported `conflict_target`.
- `DuplicateEntityError` — **not** raised by default in v1 (reserved for optional `raise_on_conflict=True` later).
- Adapter-specific DB errors propagate as today (`DatabaseError` subclasses where applicable).

## Concurrency guarantees

- **Same deterministic `id`:** at most one insert wins; losers observe `created=False` and the winner's stored payload.
- **Different ids, same business key:** not atomic in v1. Callers that need business-key uniqueness must declare a unique index **and** wait for phase 2 `conflict_target` extension, or encode the business key into a deterministic `id` (Integral pattern).

## Testing requirements

- Unit/integration: create → absent inserts; second call same id returns existing, no field overwrite.
- Concurrent: N parallel `create_if_absent` with same id → exactly one `created=True`, all return identical stored payload.
- Regression: `save()` remains upsert (`test_save_is_upsert` unchanged).
- SQLite: prove unique secondary collision via this API does **not** delete rows (contrast `OR REPLACE` hazard).
- Object-layer: rehydrate on miss; DeferredSaveMixin flush only when created.
- Adapters covered: SQLite (always), Postgres (CI postgres job), MongoDB/JsonDB as existing suite patterns allow.

## Docs / stability / release

- Document in `docs/md/entity-reference.md`, `SPEC.md` persistence section, `docs/md/stability.md` (public: `Object.create_if_absent`, `Database.insert_if_absent`, `InsertIfAbsentResult`).
- `CHANGELOG.md` under `[Unreleased]` → shipped as `[0.0.20]`.
- Bump `jvspatial/version.py` to `0.0.20` when merging to main per VERSIONING workflow.
- Export new names from public `__all__` where appropriate.

## Phase 2 (out of this PR)

- `conflict_target` naming unique indexes / compound keys from `get_indexes()`.
- Migrate webhook idempotency helper off find-then-save.
- Optional `raise_on_conflict: bool = False`.

## Success criteria

1. Concurrent identical-id creates never overwrite stored data on SQLite and Postgres.
2. `save()` behavior unchanged.
3. Public API documented and exported.
4. Integral can replace race-prone QueryResultSet create with `create_if_absent` in a follow-up bump.
