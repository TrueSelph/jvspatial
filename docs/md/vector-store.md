# Vector store (pgvector)

`PostgresDB` integrates with the
[pgvector](https://github.com/pgvector/pgvector) extension to store embeddings
alongside other entity data and run hybrid queries that combine
metadata filtering, graph traversal, and ANN similarity search in a single
SQL statement.

This is the differentiated capability for KG-driven RAG: surface the right
documents by filtering on tenant + metadata + graph hop, then re-rank by
embedding similarity — all on one round trip to Postgres.

## Install

```bash
pip install 'jvspatial[pgvector]'
```

The Postgres instance must have the `vector` extension available. On managed
services:

- **Neon**: enabled by default on every project.
- **Aurora PostgreSQL**: PG 15.4+ ships `vector`. Enable with
  `CREATE EXTENSION vector;` in your DB.
- **RDS PostgreSQL**: same as Aurora.
- **Self-hosted**: install the `pgvector` package then `CREATE EXTENSION vector;`.

The adapter calls `CREATE EXTENSION IF NOT EXISTS vector` on first
`enable_vector_column` use, so you don't need to do this manually if your
deployment role has `CREATE` privilege on the database.

## Declaring a vector column

```python
db = create_database("postgres", dsn=...)

# Add a 1536-dim embedding column on the `doc` collection.
await db.enable_vector_column("doc", "embedding", dim=1536)
```

This:

1. Creates an extension if missing.
2. Adds the column: `ALTER TABLE doc ADD COLUMN embedding vector(1536)`.
3. Builds an HNSW index on the column (or IVFFlat, see options below).
4. Registers the column with the adapter so save / find handle it
   automatically.

`enable_vector_column` is idempotent — re-running with the same dim is safe.
Changing dim requires manually dropping the column.

### Index options

```python
await db.enable_vector_column(
    "doc",
    "embedding",
    dim=1536,
    index="hnsw",            # or "ivfflat"
    ops="vector_cosine_ops", # or "vector_l2_ops" / "vector_ip_ops"
    m=16,                    # HNSW: max connections per node
    ef_construction=64,      # HNSW: build-time accuracy
)
```

| Index    | Notes                                                         |
| -------- | ------------------------------------------------------------- |
| `hnsw`   | Best recall / latency. Default. Larger memory footprint.      |
| `ivfflat`| Lower memory. Slightly worse recall. Requires `lists=` tuning. |

| Ops                  | Distance operator | When to use                          |
| -------------------- | ----------------- | ------------------------------------ |
| `vector_cosine_ops`  | `<=>`             | Default. Most LLM embeddings.        |
| `vector_l2_ops`      | `<->`             | Euclidean distance.                  |
| `vector_ip_ops`      | `<#>`             | Inner product (max similarity).      |

## Writing embeddings

Embeddings flow naturally as part of the entity payload:

```python
await db.save(
    "doc",
    {
        "id": "doc.123",
        "entity": "doc",
        "context": {"title": "Quarterly report", "status": "published"},
        "embedding": [0.012, -0.034, ...],   # length must match dim
    },
)
```

The adapter mirrors the vector field into the dedicated `embedding` column
on save. It also stays in the JSONB `data` blob so a subsequent `get()`
returns the embedding alongside the rest of the record without a second
round trip.

For bulk loading, use `bulk_save_detailed` — it uses `COPY FROM STDIN` for
the JSONB rows plus a follow-up `UPDATE` for any vectors that were set in
the batch (single round trip per batch).

## Similarity queries — `$near`

```python
results = await db.find(
    "doc",
    {"embedding": {"$near": query_vector, "$limit": 10}},
)
```

`$near` peels off into an `ORDER BY embedding <=> $1::vector LIMIT 10`
appended to the SQL — single statement, single round trip. The `$limit`
piggybacks on the operator (LIMIT and ORDER BY want to compose with the
distance operator at the SQL level).

If you also pass a top-level `limit=`, the smaller of the two wins.

## Hybrid queries — KG + metadata + vector

This is the load-bearing capability. Combine arbitrary jvspatial query
operators with `$near` in a single `find()`:

```python
results = await db.find(
    "doc",
    {
        # Metadata filter
        "context.status": "published",
        "context.workspace_id": {"$in": allowed_workspaces},
        # Vector similarity (peeled into ORDER BY)
        "embedding": {
            "$near": query_vector,
            "$limit": 50,
        },
    },
)
```

Translates to one SQL statement:

```sql
SELECT data FROM doc
WHERE (data #>> '{context,status}') = 'published'
  AND (data #>> '{context,workspace_id}') = ANY($1::text[])
ORDER BY embedding <=> $2::vector
LIMIT 50;
```

The Postgres planner can use:

- The default GIN index for the JSONB filter.
- The HNSW index for the ANN ordering.
- The RLS predicate for tenant isolation (if `enable_rls` was called).
- A walker recursive CTE (if you scope the query to a graph subtree).

All in one round trip, all transactional. This is the architectural payoff
of putting embeddings in Postgres rather than a separate vector store.

## Graph + vector composition

Combine `traverse()` and `$near` to do "find docs related to this entity
within 2 hops, then rank by relevance to my query":

```python
# 1. Walk the KG.
neighbors = await db.traverse(
    "edge",
    start_id=entity_id,
    direction="out",
    max_depth=2,
)
neighbor_ids = [n["node_id"] for n in neighbors]

# 2. Filter + vector-rank in one query.
results = await db.find(
    "doc",
    {
        "id": {"$in": neighbor_ids},
        "embedding": {"$near": query_vector, "$limit": 10},
    },
)
```

Both steps are single round trips. The KG hop replaces what would have been
N find-by-source queries on document backends; the vector rank stays in PG
instead of round-tripping to an external vector service.

## Limitations

- One vector column per `$near` per query. Multi-vector queries (e.g.
  "near both A and B") require multiple `find()` calls and application-layer
  fusion.
- The vector column is stored separately from `data` JSONB but kept in sync
  on save — embeddings are intentionally NOT indexed by the default GIN. Use
  the HNSW / IVFFlat index instead.
- pgvector's distance operators (`<=>`, `<->`, `<#>`) only work as operators
  inside SQL — there's no `data #> ...` shorthand for vectors. That's why the
  adapter routes them via the dedicated column.

## See also

- [postgres-guide.md](postgres-guide.md)
- [multi-tenant-rls.md](multi-tenant-rls.md)
- [pgvector documentation](https://github.com/pgvector/pgvector)
