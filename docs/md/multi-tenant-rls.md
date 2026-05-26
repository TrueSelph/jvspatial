# Multi-tenant Row-Level Security (Postgres)

`PostgresDB` supports per-tenant data isolation using PostgreSQL Row-Level
Security. The policy is enforced **in the database**, so a misconfigured
query or a SQL-injection vulnerability in application code cannot leak rows
across tenants. This is the cleanest path to multi-tenant SaaS on jvspatial
and the load-bearing isolation primitive for the
[Integral](https://example.com) platform.

## How it works

1. Each row carries a `tenant_id` column (auto-added by the table schema).
2. `enable_rls(collection)` installs an RLS policy:
   ```sql
   tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
   ```
3. Each request enters a `db.tenant(...)` async context, which opens a
   transaction and runs `SELECT set_config('app.tenant_id', '<tid>', true)`
   before any query.
4. Postgres applies the policy at the storage layer — queries see only rows
   matching the GUC. Inserts (via `WITH CHECK`) are likewise restricted.

## Adoption

```python
from jvspatial import create_database

db = create_database("postgres", dsn="postgresql://app:pw@host/dbname")

# At app startup, enable RLS on every multi-tenant collection.
await db.enable_rls("user")
await db.enable_rls("project")
await db.enable_rls("document")
```

`enable_rls` is idempotent — re-running on a collection with an existing
policy drops and recreates it (so policy edits land cleanly).

## Per-request scoping

Wrap each request's database work in `db.tenant(...)`:

```python
async def handle_request(request, db):
    tenant_id = request.headers["X-Tenant-Id"]
    async with db.tenant(tenant_id):
        users = await User.find()       # only this tenant's users
        await Document.create(...)      # tenant_id is stamped automatically
```

The tenant scope uses `contextvars`, so:

- Nested scopes shadow correctly:
  ```python
  async with db.tenant("acme"):           # outer
      async with db.tenant("admin-tool"): # inner — admin work on a different tenant
          await do_admin_work()
  ```
- Sibling async tasks have independent scopes:
  ```python
  await asyncio.gather(
      serve(request_a),  # may set tenant("acme")
      serve(request_b),  # may set tenant("beta")
  )  # no cross-contamination
  ```

## Critical: do NOT connect as a superuser

PostgreSQL **superusers and roles with `BYPASSRLS` bypass RLS entirely**, even
when `FORCE ROW LEVEL SECURITY` is set on the table. RLS is a no-op for those
roles by design.

For production:

```sql
CREATE ROLE app_user
    WITH LOGIN PASSWORD 'redacted'
    NOSUPERUSER NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT ALL ON ALL TABLES IN SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO app_user;
```

Then point jvspatial at the unprivileged role:

```
postgresql://app_user:pw@host/dbname
```

The schema-bootstrap step (CREATE TABLE / CREATE INDEX / CREATE EXTENSION)
*can* run as a privileged role at deploy time; the **runtime app** must
authenticate as the unprivileged role.

This is enforced as a hard requirement — without it, RLS provides zero
protection. Treat connecting as a non-superuser the same way you treat HTTPS:
non-negotiable for production.

## `tenant_required=False` (single-tenant migration)

If you're migrating an existing single-tenant application incrementally, pass
`tenant_required=False`:

```python
await db.enable_rls("user", tenant_required=False)
```

The policy becomes:

```sql
tenant_id IS NULL
OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')
```

Rows with `tenant_id = NULL` form a "global" partition visible to every
session. Use this only during migration — flip back to `tenant_required=True`
once all rows are tenant-tagged.

## Insertion behavior

When `db.tenant(tid)` is active, `save()` writes the GUC's tenant_id into the
row, so callers don't need to set `tenant_id` explicitly:

```python
async with db.tenant("acme"):
    await db.save("project", {"id": "p.1", "context": {"name": "Project 1"}})
# Row stored with tenant_id='acme'.
```

If a caller does pass `tenant_id` explicitly, the `WITH CHECK` policy enforces
that it matches the active scope — saving a record with a different tenant_id
than the current scope raises a Postgres `new row violates row-level security
policy` error.

## Testing your tenant boundary

Write the malicious-caller test:

```python
async def test_tenant_a_cannot_read_tenant_b(db):
    async with db.tenant("tenant_a"):
        await User.create(name="alice")

    async with db.tenant("tenant_b"):
        await User.create(name="bob")

    # Try to read alice from tenant_b's scope — even with crafted filters.
    async with db.tenant("tenant_b"):
        sneaky = await User.find({"context.name": "alice"})
        assert sneaky == []
        sneaky = await User.find({"$or": [{"context.name": "alice"}]})
        assert sneaky == []
        # And no raw id lookup either.
        assert await db.get("user", "<alice_id>") is None
```

The jvspatial test suite includes this exact pattern in
`tests/db/test_postgres_integration.py::TestPostgresRLS`.

## Performance

RLS adds:

- One `BEGIN` + one `SET LOCAL` per checkout when `db.tenant(...)` is active.
- One small predicate to every `WHERE` clause (`tenant_id = ...`).

The `<collection>_tenant_idx` partial index keeps the predicate cheap. In
microbenchmarks the overhead is <5% for typical record sizes and dominates
nothing past 10K row collections.

## When to use vs not

Use RLS for tenant isolation in multi-tenant SaaS — the safety guarantee is
strong and the overhead is small.

Don't use RLS for:

- **Authorization beyond tenant boundaries** (e.g. user-level ACL inside a
  tenant): use application-layer access checks. RLS is row-level, not action-
  level.
- **Fine-grained sharing** (record visible to multiple tenants): RLS expects
  a 1:N tenant-to-row relationship. Cross-tenant sharing belongs in
  application code.
- **Backends other than Postgres**: RLS is Postgres-only. The other jvspatial
  backends require application-layer tenant filtering.

## See also

- [postgres-guide.md](postgres-guide.md)
- [PostgreSQL RLS documentation](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
