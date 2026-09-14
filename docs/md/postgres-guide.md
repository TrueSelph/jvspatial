# Postgres backend — adoption guide

`jvspatial` ships with a first-class PostgreSQL backend (`PostgresDB`) built on
[asyncpg](https://github.com/MagicStack/asyncpg) and JSONB. It is the recommended
high-performance distributed backend and the default platform for serverless
deployments via Neon and Aurora Serverless v2.

This guide covers adoption, schema, pool tuning, and operational tips. For
multi-tenant isolation see [multi-tenant-rls.md](multi-tenant-rls.md). For
embedding storage and hybrid queries see [vector-store.md](vector-store.md).

## Why Postgres

The other backends each have a niche:

| Backend  | Where it shines                                    |
| -------- | -------------------------------------------------- |
| JsonDB   | Development only — human-readable, no setup        |
| SQLite   | Local production, single-binary deployments        |
| MongoDB  | Established document workloads                     |
| DynamoDB | AWS-native serverless KV at scale                  |
| **Postgres** | **High-performance OLTP + graph + vector + multi-tenant — the default for new applications** |

Postgres outperforms MongoDB on jvspatial's four primary workloads:

- **Bulk writes** — 5–20× via `COPY FROM STDIN`.
- **Hot small-doc reads** — 3–5× lower latency via asyncpg's binary protocol +
  prepared statements.
- **Walker BFS** — N round trips collapse into one recursive CTE.
- **Mongo-op coverage** — JSONB + `jsonb_path_query` pushes down `$regex`,
  `$elemMatch`, `$size`, `$mod`, `$type` natively (operators that fall back to
  in-memory match on SQLite).

Add to that ACID transactions, RLS-based multi-tenancy, and the pgvector
extension for in-database ANN, and Postgres becomes the obvious default for
production jvspatial applications.

## Install

```bash
pip install 'jvspatial[postgres]'
# Or with the vector codec for pgvector workloads:
pip install 'jvspatial[pgvector]'
```

This adds [asyncpg](https://pypi.org/project/asyncpg/) (and optionally
[pgvector](https://pypi.org/project/pgvector/)) to the install.

## Quick start

```python
from jvspatial import create_database

db = create_database(
    "postgres",
    dsn="postgresql://user:pw@localhost:5432/mydb",
    register=True,
    name="prime",
)
```

`PostgresDB` accepts the same `dsn` you'd use with `psql`. Env-driven
configuration is also supported — see the [environment variables](#environment-variables)
section below.

`Object`, `Node`, `Edge`, and `Walker` operations route through the registered
prime database with no further configuration:

```python
from jvspatial import Node

class User(Node):
    name: str = ""
    email: str = ""

alice = await User.create(name="Alice", email="alice@example.com")
loaded = await User.get(alice.id)
```

### Using Postgres with `Server`

`Server` selects the prime database from `db_type`, so Postgres is available
to the API layer the same way JSON or MongoDB is:

```python
from jvspatial.api.server import Server

server = Server(
    db_type="postgres",
    postgres_dsn="postgresql://user:pw@localhost:5432/mydb",
)
```

`postgresql` is accepted as an alias for `postgres`. Every connection setting
also resolves from the environment through `ServerConfig`:

```bash
JVSPATIAL_DB_TYPE=postgres
JVSPATIAL_POSTGRES_DSN=postgresql://user:pw@localhost:5432/mydb
```

Settings you leave unset fall through to `PostgresDB`'s own defaults, so the
DSN is the only value most deployments need. `JVSPATIAL_DB_PATH` does not
apply — it is a file-backend setting.

Note that the logging database is a separate store and has no Postgres
backend; if `JVSPATIAL_LOG_DB_TYPE` is unset it inherits `JVSPATIAL_DB_TYPE`
and falls back to a JSON file log. Set it explicitly when the graph runs on
Postgres.

## Schema

Each collection becomes one table. The shape:

```sql
CREATE TABLE <collection> (
    id         TEXT PRIMARY KEY,
    entity     TEXT NOT NULL,
    tenant_id  TEXT,            -- NULL when not using multi-tenancy
    data       JSONB NOT NULL,
    _v         INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX <collection>_data_gin
    ON <collection> USING GIN (data jsonb_path_ops);
CREATE INDEX <collection>_entity_idx
    ON <collection> (entity);
CREATE INDEX <collection>_tenant_idx
    ON <collection> (tenant_id) WHERE tenant_id IS NOT NULL;
```

The full record lives in the `data` JSONB blob. `id`, `entity`, and `tenant_id`
are denormalized for indexing. The whole-document GIN index on `data` only
accelerates containment-shaped predicates (`$all`); see
[Index policy](#index-policy) for when to turn it off.

### Index policy

- **Per-class indexes lead with `entity`.** Every typed `find()` filters on
  the `entity` column of a table shared by every class, so an index declared
  with `attribute(indexed=True)` or `@compound_index(...)` is created as
  `(entity, <fields>)` and named `<col>_entity_<fields>_idx`. Sibling classes
  that declare the same fields share it. Pass `index_partial_by_entity=True`
  (or `@compound_index(..., partial_by_entity=True)`) for a smaller
  `WHERE entity = '<Class>'` index per class instead, or
  `entity_leading=False` to keep the key unscoped. The pre-0.0.18 unscoped
  index of the same fields is dropped when its replacement is created.
- **Descending keys are `DESC NULLS LAST`**, the order `find(sort=...)`
  emits, so `sort=[("context.created_at", -1)], limit=20` walks the index
  with no sort step. Indexes created by 0.0.17 and earlier (descending keys
  without `NULLS LAST`, or `entity` / `id` indexed as JSONB paths — e.g. the
  edge `(source, target, entity)` unique index) are rebuilt in place the next
  time `ensure_indexes` runs.
- **The whole-document GIN is optional.** `JVSPATIAL_PG_GIN_INDEX=off` (or
  `create_database("postgres", ..., gin_index="off")`) stops new
  collections from creating `<col>_data_gin`. Every node rewrite re-indexes
  the whole document into that GIN, while equality / range / sort use the
  functional B-trees above. Large deployments should turn it off, then drop
  an existing one with `DROP INDEX CONCURRENTLY node_data_gin;` —
  `find()` logs a one-time warning if an `$all` / `$elemMatch` query then
  runs without it.

### Full-text search

```python
from jvspatial.core.annotations import attribute, fulltext_index

@fulltext_index(["title", "body"])          # one GIN over both fields
class Article(Node):
    title: str = ""
    body: str = ""
    summary: str = attribute(fulltext=True, default="")  # or per-attribute

await Article.find({"$text": {"$search": "graph database",
                              "$fields": ["context.title", "context.body"]}})
```

`$text` becomes `to_tsvector('simple', …) @@ plainto_tsquery('simple', …)`:
every search word must appear (case-insensitive, no stemming — "database"
does not match "databases"). The index is used when `$fields` lists the same
fields in the same order as the declaration. Other backends evaluate the same
semantics in memory; MongoDB searches its own text index.

`$regex` is never index-backed. When a pattern has to include user input, pass
the input through `jvspatial.db.escape_regex` so metacharacters match
literally (and a crafted pattern cannot make every scan slow).

### Custom indexes

```python
# Functional B-tree on a JSONB field path
await db.create_index("user", "context.email", unique=True)

# Compound index
await db.create_index("user", [("context.country", 1), ("context.signup_at", -1)])

# Partial index (Postgres-specific kwarg)
await db.create_index(
    "user",
    "context.status",
    where="(data #>> '{context,status}') = 'active'",
)
```

Vector columns (pgvector) are added via the dedicated helper:

```python
await db.enable_vector_column("doc", "embedding", dim=1536)
```

See [vector-store.md](vector-store.md) for details.

### Node adjacency lives in the `edge` table

Node rows carry no `edges` array. Adjacency is read from the `edge` table
through the `source` / `target` functional indexes that `Edge.get_indexes()`
declares, so `connect()`, `disconnect()` and `save()` cost the same on a node
with ten edges as on one with a hundred thousand, and concurrent writers never
queue on a hub's row lock. Keep index auto-creation on
(`JVSPATIAL_AUTO_CREATE_INDEXES`, default on outside serverless) or run
`ensure_indexes(Edge)` at deploy time — without those indexes every adjacency
read scans the `edge` table.

Rows written by 0.0.17 and earlier may still carry the array. Reads ignore it
and the next save of each node drops it; to reclaim the space in one pass:

```bash
jvspatial migrate strip-node-edges --dsn "$JVSPATIAL_POSTGRES_DSN"          # dry run: count rows
jvspatial migrate strip-node-edges --dsn "$JVSPATIAL_POSTGRES_DSN" --apply  # strip, batched
```

It is idempotent and safe while the application serves traffic (saves never
write the array back). Tables with `FORCE ROW LEVEL SECURITY` must be
migrated by a role that bypasses RLS. Afterwards run `VACUUM (ANALYZE) node`
and `REINDEX INDEX CONCURRENTLY node_data_gin` to return the space.

## Pool tuning

`PostgresDB` runs on a single `asyncpg.Pool` per instance, created lazily on
first use. Pool sizing auto-tunes based on
[`is_serverless_mode()`](serverless-mode.md):

| Deployment       | Default `min_size` | Default `max_size` |
| ---------------- | ------------------ | ------------------ |
| Long-running     | 2                  | 10                 |
| Serverless (Lambda / GCF / Azure Functions) | 0 | 3 |

Override via constructor kwargs:

```python
db = create_database("postgres", dsn=..., min_size=5, max_size=25)
```

Or via env (see [environment-keys-reference.md](environment-keys-reference.md)):

```bash
JVSPATIAL_POSTGRES_MIN_POOL_SIZE=5
JVSPATIAL_POSTGRES_MAX_POOL_SIZE=25
JVSPATIAL_POSTGRES_COMMAND_TIMEOUT=30   # per-statement timeout, seconds (default 60)
```

**Sizing rule of thumb.** Postgres does useful work on roughly two active
connections per database CPU core, and every open connection costs server
memory. Size the pools so their sum stays near that budget:

```text
max_size ≈ (2 × DB host cores) ÷ number of app processes
```

Four app workers against an 8-core database: `max_size ≈ 16 ÷ 4 = 4`. A
bigger pool mostly moves the queue from the pool into Postgres. Keep
`max_size × processes` well below `max_connections`. For many short-lived
processes (Lambda, autoscaled containers) put PgBouncer / RDS Proxy in front
and size the pooler, not each process — see below.

### Event loops

The pool belongs to the event loop that created it. If a host bootstraps
inside one `asyncio.run()` and then serves from a second loop — the common
CLI-then-ASGI-server startup — `PostgresDB` notices the loop change and
rebuilds the pool on first use in the new loop. The abandoned pool's
connections are dropped rather than closed, since closing them would mean
awaiting on a loop that no longer runs.

### Pooler compatibility (PgBouncer / RDS Proxy)

Transaction-mode poolers (PgBouncer transaction-pooling, AWS RDS Proxy) reuse
connections across transactions, which breaks prepared statements. Opt into
the simple-query protocol with `pooler_mode="transaction"`:

```python
db = create_database("postgres", dsn=..., pooler_mode="transaction")
```

This disables asyncpg's statement cache (`statement_cache_size=0`) and binds
parameters with the simple-query path, at the cost of some per-query overhead.
Use it only when you're behind a transaction-pooling layer; direct or
session-pooled connections should keep the default `pooler_mode="session"`.
Set it by environment with `JVSPATIAL_POSTGRES_POOLER_MODE=transaction`.

Tenant scoping (`db.tenant(...)`) is transaction-pooler safe: every scoped
operation runs inside one transaction that begins with
`SELECT set_config('app.tenant_id', $1, true)` (a `SET LOCAL`), so the GUC
never leaks to the next client of a pooled server connection.

## Transactions

`PostgresDB.supports_transactions = True`. Use the standard `transaction_context`
helper:

```python
from jvspatial.db.transaction import transaction_context

async with transaction_context(db) as txn:
    if txn is None:
        # Backend doesn't support transactions; handle accordingly.
        ...
    else:
        await txn.save("user", user_record)
        await txn.save("audit_log", log_record)
        # Commits on context exit; rolls back on exception.
```

The transaction holds one dedicated connection out of the pool for its
lifetime, so be careful not to hold transactions across long-running awaits.

## Bulk writes

The fast path is `bulk_save_detailed`, which uses `COPY FROM STDIN` into a
temp table then a single `INSERT ... ON CONFLICT DO UPDATE` merge:

```python
records = [{"id": f"u{i}", "entity": "user", "context": {...}} for i in range(50_000)]
result = await db.bulk_save_detailed("user", records)
assert result.all_saved
```

Expect 5–20× over per-record `save()` calls for batches >100 records.

If the fast path fails (e.g. a row violates a constraint), the adapter falls
back to per-record saves so callers see exactly which IDs failed in
`result.failed_ids`.

## Environment variables

`PostgresDB` reads the following on initialization (constructor kwargs take
precedence):

| Variable                                | Purpose                                            |
| --------------------------------------- | -------------------------------------------------- |
| `JVSPATIAL_POSTGRES_DSN`                | Default connection string                          |
| `JVSPATIAL_POSTGRES_MIN_POOL_SIZE`      | Pool min size override                             |
| `JVSPATIAL_POSTGRES_MAX_POOL_SIZE`      | Pool max size override                             |
| `JVSPATIAL_POSTGRES_POOLER_MODE`        | `"session"` (default) or `"transaction"`           |
| `JVSPATIAL_POSTGRES_COMMAND_TIMEOUT`    | Per-statement timeout in seconds (default 60)      |
| `JVSPATIAL_PG_GIN_INDEX`                | `"full"` (default) or `"off"` — whole-document GIN |

## Operational tips

- **VACUUM / ANALYZE** runs automatically via autovacuum; if you do bulk loads
  followed by immediate read-heavy workloads, run `ANALYZE <collection>` to
  refresh planner stats.
- **Connection limit**: keep `max_size × app instances` comfortably under
  `max_connections` on the server. For serverless deployments behind a pooler,
  `max_size=2–3` per Lambda is normal.
- **Backups**: standard `pg_dump` or managed-service snapshots work as-is.
  `data` is a JSONB blob, so dumps preserve the application schema verbatim.
- **Migrations**: when schema-evolving an `Object`, write the migration through
  the jvspatial migration registry (Phase E roadmap item — coming soon).
  Meanwhile, raw SQL migrations against the `data` JSONB blob work as a
  manual fallback.

## See also

- [multi-tenant-rls.md](multi-tenant-rls.md) — per-tenant isolation with RLS
- [vector-store.md](vector-store.md) — pgvector + hybrid queries
- [neon-deployment.md](neon-deployment.md) — Neon-specific notes
- [aurora-serverless-deployment.md](aurora-serverless-deployment.md) — Aurora SLv2
- [optimization.md](optimization.md) — cross-backend performance guidance
