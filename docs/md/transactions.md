# Transactions

Native transactions are available on PostgreSQL and on transaction-capable
MongoDB deployments. JSON, SQLite and DynamoDB do not advertise native
transactions. Single-record atomic writes on those stores are not multi-write
rollback or cross-store atomicity.

## Capability and lifecycle

Check `db.supports_transactions`, rather than detecting an adapter class.
MongoDB requires a replica set or sharded cluster. Its static support flag
identifies the adapter feature; `await db.is_transactional()` probes the
deployment. The flag alone does not prove topology support. Unsupported `transaction_context` yields `None` by default.
Callers requiring atomic work must reject that case rather than silently
performing unprotected writes.

```python
from jvspatial.db import create_database
from jvspatial.db.transaction import transaction_context

db = create_database("postgres", dsn="postgresql://localhost/mydb")
async with transaction_context(db) as tx:
    if tx is None:
        raise RuntimeError("This operation requires native transactions")
    await tx.save("object", {
        "id": "o.Record.example",
        "entity": "Record",
        "context": {"state": "ready"},
    })
    ids = await tx.find_ids("object", {"entity": "Record"}, limit=20)
    records = await tx.find_many("object", ids)
    total = await tx.count("object", {"entity": "Record"})
```

Normal exit commits; an exception or cancellation rolls back. Keep external network calls and
long computation outside the transaction. A PostgreSQL handle owns one pool
connection until exit, and rejects operations after it has completed. Concurrent
operations on that handle are serialized to prevent overlapping asyncpg
commands; callers still own application-level coordination of mutable entities.
New collection creation and its indexes run on the held connection, so a
one-connection pool does not require a second connection for bootstrap.
Rollback discards pending bootstrap cache entries. MongoDB commit/rollback
await session cleanup for both asynchronous driver shapes.

## Read contract

| Method | Result | Implementation |
| --- | --- | --- |
| `get(collection, id)` | Record or `None` | Native transaction read |
| `find(collection, query, sort=, limit=)` | Record list | Native transaction read |
| `find_one(collection, query)` | Record or `None` | One matching record |
| `count(collection, query=None)` | Integer | PostgreSQL native count; shared fallback reads transaction-visible matches |
| `find_ids(collection, query, limit=, sort=, offset=)` | Ordered ID list | PostgreSQL native projection; shared fallback retains deterministic ID tie-breaking |
| `find_many(collection, ids)` | ID-to-record dictionary | PostgreSQL native set read; shared fallback uses handle-local `get` |
| `find_iter(collection, query, sort=, batch_size=, cursor=)` | Async iterator | Shared composite-keyset paging through transaction reads |
| `count_incident_edges(collection, node_ids)` | ID-to-degree dictionary | Shared transaction-visible edge count |

Fallbacks preserve the same connection/session and visibility, but may perform
more work than native aggregates or projections. In particular, the MongoDB
shared count and ID projection can materialize records, and shared multi-get
is sequential. They are correctness fallbacks, not a claim of identical
round-trip counts or performance across adapters. Iteration requires a positive
batch size and preserves every sort key plus ID in continuation. Backend-native
ordering differences remain documented in [Cursor Pagination](cursor-pagination.md).

## Entity and graph operations

Raw transaction methods operate on database records. Entity `save`/`get` and
relationship operations must use `graph_transaction` to bind their context to
the transaction handle; using the outer database explicitly escapes that scope.
If a deployment returns no transaction, `graph_transaction` raises
`TransactionUnavailable` before binding a context. It never silently falls back
to the outer store. Every application-created Node still needs its normal rooted structural edge
in the same transaction.

```python
from jvspatial.core import graph_transaction

# Item is an application-defined Node already attached to its application root.
async with graph_transaction(db):
    item = await Item.get(item_id)
    if item is not None:
        item.title = new_title
        await item.save()
```

A graph transaction gets an isolated request identity map. It neither returns
outer-context objects from the shared cache nor publishes uncommitted objects
into that cache. An explicitly selected different context does not reuse an
identity-map entry bound to the transaction. Touched parent cache keys are
invalidated after commit and rollback. Archived application state and any
long-lived object references remain the application's responsibility.

PostgreSQL's active `db.tenant(...)` scope is carried onto the held transaction
connection with transaction-local settings. This supports an application's
configured RLS policy; it does not create an access policy or replace
application authorization.

## Monitoring and limits

The optional observable wrapper records metrics and failure-only ERROR logs
for operations invoked through that wrapper. It forwards native transaction
handles; raw handle operations are not automatically instrumented as wrapped
database operations. Successful calls, including slow calls, never produce
routine observation logs. See [Observability](observability.md).

Use backend-specific integration tests to qualify rollback, tenant scope,
concurrency and deployed MongoDB topology. Neither the shared API nor an
in-memory test double proves cross-store atomicity or live replica-set behavior.
