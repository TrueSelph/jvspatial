# Aurora Serverless v2 deployment guide

[Amazon Aurora Serverless v2](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.html)
is the recommended managed Postgres for jvspatial deployments inside AWS,
especially when paired with Lambda + LWA (Lambda Web Adapter). This guide
covers the configuration knobs that matter for jvspatial workloads and the
RDS-Proxy compatibility you'll want for high-concurrency Lambda.

## At a glance

| Feature                       | Aurora Serverless v2                          |
| ----------------------------- | --------------------------------------------- |
| Cold start (`min_capacity=0`) | ~15–30s scale-from-zero                       |
| Cold start (`min_capacity=0.5`) | <1s — recommended for latency-sensitive paths |
| Compute granularity           | 0.5 ACU increments, scales sub-second once warm |
| pgvector                      | Available on PG 15.4+                         |
| Connection pooling            | Add RDS Proxy for transaction-mode pooling    |
| AWS-native                    | IAM auth, VPC, KMS, Secrets Manager           |
| HA / Multi-AZ                 | Built-in                                      |

## DSN format

```bash
JVSPATIAL_POSTGRES_DSN="postgresql://app_user:pw@<cluster-endpoint>:5432/jvdb"
```

For cross-AZ failover correctness, use the **writer endpoint**
(`<cluster>.cluster-XXX.region.rds.amazonaws.com`). For read-replica routing,
the **reader endpoint** can be used, but stick with the writer for general
jvspatial workloads.

## Capacity tuning

```
Aurora Serverless v2 capacity: min_capacity ... max_capacity ACUs.
```

| Workload                              | Recommended capacity              |
| ------------------------------------- | --------------------------------- |
| Background workers / async agents     | `min=0.5, max=4`                  |
| Latency-sensitive API                 | `min=1, max=8`                    |
| Bulk-load tools (occasional spikes)   | `min=0.5, max=16`                 |
| Heavy multi-tenant SaaS               | `min=2, max=16+`                  |

**Do not use `min_capacity=0`** for any path that has user-facing latency
budgets. Scale-from-zero takes ~15–30s — long enough to time out a Lambda
invocation. For batch / background workloads, `min=0` is fine; pay the cold
start once per batch.

## RDS Proxy + transaction-mode pooling

When running jvspatial behind AWS Lambda with high concurrency, each Lambda
instance opens its own asyncpg pool. Total connection count = `Lambda
concurrency × pool max_size`. This exhausts Aurora's connection limit
quickly without RDS Proxy.

### Setup

1. Create an RDS Proxy targeting your Aurora cluster.
2. Configure it for the same DB user as the app.
3. Set the proxy endpoint as the DSN host.
4. Enable transaction mode (in the proxy's "Connection pooling configuration").

### App configuration

Transaction-mode poolers don't preserve prepared statements across the pool.
Tell asyncpg to use the simple-query path:

```bash
JVSPATIAL_POSTGRES_DSN="postgresql://app_user:pw@<proxy-endpoint>:5432/jvdb"
JVSPATIAL_POSTGRES_POOLER_MODE=transaction
```

Or via constructor kwarg:

```python
db = create_database(
    "postgres",
    dsn="postgresql://app_user:pw@<proxy-endpoint>:5432/jvdb",
    pooler_mode="transaction",
)
```

### Pool sizing on Lambda with RDS Proxy

```bash
JVSPATIAL_POSTGRES_MIN_POOL_SIZE=0
JVSPATIAL_POSTGRES_MAX_POOL_SIZE=2
```

`is_serverless_mode()` auto-tunes to (0, 3) when running on Lambda — that's a
reasonable default for most workloads.

## pgvector on Aurora

Available on Aurora PostgreSQL 15.4+. To enable:

```sql
CREATE EXTENSION vector;
```

You'll need a role with the `rds_superuser` membership (or the cluster's
master user) to run `CREATE EXTENSION` once per cluster. After that,
ordinary roles can use the type and operators.

The `db.enable_vector_column(...)` call runs `CREATE EXTENSION IF NOT EXISTS`
on first use — works fine if your deploy role has the privilege, otherwise
do it manually as part of the cluster bootstrap.

## IAM auth (optional)

To use IAM instead of password auth:

1. Enable IAM authentication on the Aurora cluster.
2. Generate a short-lived token per connection via `boto3`:

```python
import boto3
rds = boto3.client("rds")
token = rds.generate_db_auth_token(
    DBHostname="...", Port=5432, DBUsername="app_user", Region="us-east-1"
)
dsn = f"postgresql://app_user:{token}@host:5432/jvdb?sslmode=require"
```

IAM tokens expire after 15 minutes, so for long-running pools you'll need to
rotate the connection (close + reopen) periodically. For short-lived Lambdas
this is a non-issue.

## Multi-tenant RLS

RLS works as documented in [multi-tenant-rls.md](multi-tenant-rls.md). The
critical caveat applies here too: the runtime app user must NOT be a
`rds_superuser`. Create a dedicated role:

```sql
CREATE ROLE jvspatial_app
    WITH LOGIN PASSWORD :'pw'
    NOSUPERUSER NOBYPASSRLS;
GRANT CONNECT ON DATABASE jvdb TO jvspatial_app;
GRANT USAGE ON SCHEMA public TO jvspatial_app;
GRANT ALL ON ALL TABLES IN SCHEMA public TO jvspatial_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON TABLES TO jvspatial_app;
```

## Cost notes

- ACU-hours are billed in 0.5 increments. `min_capacity=0.5` runs you ~$0.06/hr
  in us-east-1 even at idle — a worthwhile floor for latency-sensitive paths.
- Cold scale-from-zero is "free" only in that you pay no ACU during idle,
  but the latency cost on the first invocation is high.
- RDS Proxy adds a separate per-hour charge — usually worth it if Lambda
  concurrency exceeds ~10.
- pgvector storage adds to the I/O + storage costs; HNSW indexes can be
  large for high-cardinality embedding columns.

## See also

- [postgres-guide.md](postgres-guide.md)
- [neon-deployment.md](neon-deployment.md) — for non-AWS deployments
- [serverless-mode.md](serverless-mode.md) — jvspatial's serverless detection
- [Aurora Serverless v2 docs](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.html)
- [RDS Proxy docs](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.html)
