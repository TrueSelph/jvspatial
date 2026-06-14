# Neon deployment guide

[Neon](https://neon.tech) is the recommended managed Postgres for serverless
jvspatial deployments outside of AWS. It offers a scale-to-zero serverless
Postgres with branching, pgvector enabled by default, and a connection
pooler that interacts cleanly with jvspatial's `pooler_mode="transaction"`.

## At a glance

| Feature                            | Neon                            |
| ---------------------------------- | ------------------------------- |
| Cold start (compute resume)        | ~500ms typical                  |
| Scale to zero                      | Default; configurable           |
| pgvector                           | Enabled out of the box          |
| Connection pooler                  | Built-in (`-pooler` endpoint)   |
| Branching for previews             | First-class                     |
| Free tier                          | Yes (storage + compute hours)   |

## DSN format

Neon gives you two endpoints per branch:

- **Direct**: `ep-XXX.region.aws.neon.tech` — direct connection. Use for
  long-running app servers when you need session-pooled connections.
- **Pooler**: `ep-XXX-pooler.region.aws.neon.tech` — transaction-mode pooler.
  Use for Lambda / Cloud Functions / any short-lived serverless runtime.

```bash
# Long-running deployment (direct)
JVSPATIAL_POSTGRES_DSN="postgresql://user:pw@ep-xxx.us-east-2.aws.neon.tech/jvdb?sslmode=require"

# Serverless deployment (pooler)
JVSPATIAL_POSTGRES_DSN="postgresql://user:pw@ep-xxx-pooler.us-east-2.aws.neon.tech/jvdb?sslmode=require"
JVSPATIAL_POSTGRES_POOLER_MODE=transaction
```

`?sslmode=require` is required by Neon and supported by asyncpg
out of the box.

## Pool sizing

For Lambda / Vercel / Cloud Run instances (where instances are short-lived
and concurrency is low per instance):

```bash
JVSPATIAL_POSTGRES_MIN_POOL_SIZE=0
JVSPATIAL_POSTGRES_MAX_POOL_SIZE=2
```

For long-running containers (ECS Fargate, GKE, EKS, Heroku-style):

```bash
JVSPATIAL_POSTGRES_MIN_POOL_SIZE=2
JVSPATIAL_POSTGRES_MAX_POOL_SIZE=10
```

`is_serverless_mode()` auto-tunes to these defaults if you don't set them.

## Branching for preview environments

Neon's branching lets you spin up a copy of your production database for each
preview deployment in seconds, with copy-on-write storage so the cost is
minimal.

For multi-tenant SaaS preview environments:

1. Branch production: `neon branches create --name pr-123-preview`.
2. Set the preview's `JVSPATIAL_POSTGRES_DSN` to the branch endpoint.
3. RLS policies and tenant data come along with the branch — preview sees
   real tenant boundaries.

This integrates well with jvspatial's [multi-tenant RLS](multi-tenant-rls.md):
test PR-scoped UI flows against tenant-isolated branches before merging.

## pgvector

`vector` is available on every Neon project by default — no extension install
step. The first `db.enable_vector_column(...)` call still runs
`CREATE EXTENSION IF NOT EXISTS vector` for portability (no-op when already
installed).

## Scale-to-zero

Neon compute scales to zero when idle (default: 5 minutes). Cold starts
typically resume in 300–600ms. For latency-sensitive APIs:

- Use Neon's "always active" configuration in the project settings, or
- Set a higher autosuspend timeout (e.g. 30 minutes), or
- Use a warm-up cron job hitting a simple endpoint every few minutes.

For background-worker / agent traffic, scale-to-zero is usually fine — the
~500ms first-query latency is amortized over the agent run.

## Credentials & secrets

- Generate a dedicated **non-superuser** role for jvspatial. Neon's
  `neon_superuser` role bypasses RLS — see
  [multi-tenant-rls.md](multi-tenant-rls.md#critical-do-not-connect-as-a-superuser).
- Rotate credentials via Neon's "Reset password" UI; the DSN format above
  picks up new credentials on next pool refresh (next cold start or
  `db.close()` + reinitialize).

## Cost notes

- Storage is charged per GB stored (compressed).
- Compute is charged per "compute unit hour" while active. Scale-to-zero
  means you pay nothing during idle periods.
- pgvector's HNSW index storage adds to GB-stored cost but does not change
  compute pricing.
- Branching is free up to the project's branch limit; each branch counts
  against your storage quota only for diverged data.

## See also

- [postgres-guide.md](postgres-guide.md)
- [aurora-serverless-deployment.md](aurora-serverless-deployment.md)
- [Neon docs](https://neon.tech/docs)
