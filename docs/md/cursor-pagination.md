# Cursor pagination

`Database.find()` materializes the entire result set in memory.
That's fine for small collections; it falls over once you're paging
through 10k+ records, especially in serverless environments where
the working memory budget is tight.

`Database.find_iter()` (also surfaced as `Object.find_iter()`) yields
records one at a time, fetching them in pages of a configurable size.
Memory stays constant regardless of result-set size, and the iteration
can be paused + resumed across processes via opaque cursors.

## Basic usage

```python
from jvspatial import Node

class User(Node):
    name: str = ""
    active: bool = False

# Stream every active user.
async for user in User.find_iter({"context.active": True}):
    await process(user)
```

The iterator handles pagination internally — each `await` of the
generator triggers the next batch fetch only when needed. Memory at
any moment holds at most `batch_size` records.

## Tuning batch size

```python
async for user in User.find_iter(batch_size=500):
    ...
```

| `batch_size` | When to pick                                                  |
| ------------ | ------------------------------------------------------------- |
| `1–20`       | Low-latency UI streaming                                      |
| `100`        | Default — balances round-trip cost vs memory                  |
| `500–2000`   | Throughput-oriented background jobs                           |
| `> 5000`     | Rarely worth it — diminishing returns vs DB memory pressure   |

For Postgres the per-page round trip is one SQL statement against the
GIN-indexed JSONB column; for MongoDB it's one motor cursor advance.
The amortized cost is essentially zero past `batch_size = 100`.

## Resuming with cursors

`find_iter` accepts an opaque `cursor` to pick up where a prior call
left off. Useful for:

* Checkpointing a long-running migration / job.
* Pagination across HTTP requests (encode the cursor into a query
  parameter; clients pass it back on the next request).

```python
from jvspatial.db.database import encode_cursor

# Process the first 1000 records, then save the cursor.
seen = 0
last_id = None
async for user in User.find_iter(batch_size=100):
    await process(user)
    last_id = user.id
    seen += 1
    if seen >= 1000:
        break

checkpoint = encode_cursor({"id": last_id})

# Later (different process), resume:
async for user in User.find_iter(batch_size=100, cursor=checkpoint):
    await process(user)
```

The cursor is `base64(json({"id": "<last_seen_id>"}))` — fully opaque
to the caller, debuggable on demand.

## Backend implementations

| Backend     | Implementation                                                                      |
| ----------- | ----------------------------------------------------------------------------------- |
| **Postgres**| Native keyset pagination via `WHERE id > $last ORDER BY id LIMIT $batch_size`. One pool connection held for the iteration; GIN + functional indexes on JSONB still apply to the filter. |
| MongoDB     | Default implementation — one `find(... limit=batch_size)` per page using keyset on `id`. Can be optimized to native motor cursor in a future release. |
| SQLite      | Default implementation — `SELECT ... WHERE id > ? ORDER BY id LIMIT ?` per page; aiosqlite single-connection model means no pool overhead. |
| DynamoDB    | Default implementation works; can be optimized to native `LastEvaluatedKey` later. |
| JsonDB      | Default implementation — loads each page via `find(limit=batch_size)`. Acceptable since JsonDB is dev-only. |

All backends honor the same cursor format, so callers don't need to
care which backend they're on when serializing checkpoints.

## Consistency notes

Keyset pagination on `id` (the default) is consistent under concurrent
inserts:

* New rows inserted with an ID *less than* the last-seen ID are not
  visited (they'd require backing up; that's a different operation).
* New rows inserted with an ID *greater than* the last-seen ID **are**
  visited.
* Rows updated to change their `id` between batches — don't do this.
  IDs are immutable by SPEC §1.1.

For strict exactly-once semantics across long iterations, snapshot
the query inside a transaction:

```python
from jvspatial.db.transaction import transaction_context

async with transaction_context(db) as txn:
    if txn is not None:
        async for record in txn.find("user", {}):
            ...
```

(Note: `find_iter` is not yet wired through the transaction handle for
all backends — use it from outside the transaction when consistency
isn't critical, or fall back to `txn.find` for snapshotted reads.)

## Sort + filter composition

`find_iter` accepts both `sort` and `query`:

```python
async for user in User.find_iter(
    {"context.active": True},
    sort=[("context.created_at", -1)],
    batch_size=200,
):
    ...
```

On Postgres the sort + filter compose into one SQL statement with the
keyset filter as a tiebreaker on `id`. Other backends apply sort
in-memory on each batch (acceptable for moderate batch sizes; if you
need stable sort across a huge result set, prefer Postgres).

## See also

- [postgres-guide.md](postgres-guide.md) — schema + indexes that make
  large-page iteration cheap.
- [schema-migrations.md](schema-migrations.md) — bulk-migration CLI
  uses the same scan pattern under the hood.
