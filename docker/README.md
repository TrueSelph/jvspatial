# Local Postgres for jvspatial

Dockerized Postgres 16 + pgvector for testing jvspatial apps against PG.

## Start

```bash
cd docker
docker compose up -d
```

Healthcheck takes ~5s. Verify:

```bash
docker compose ps
docker compose logs -f postgres   # tail logs
```

## Connect

```
postgresql://jvspatial:jvspatial@localhost:5432/jvspatial
```

Copy `.env.example` to project root `.env` for `JVSPATIAL_*` / `DATABASE_URL` consumers.

Psql shell:

```bash
docker exec -it jvspatial-pg psql -U jvspatial -d jvspatial
```

## Extensions

Loaded on first init via `pg-init/01-extensions.sql`:
- `vector` (pgvector) — embeddings / similarity search
- `pg_trgm` — trigram text search
- `btree_gin` — composite GIN indexes
- `uuid-ossp` — UUID generation

Re-apply on existing volume:

```bash
docker exec jvspatial-pg psql -U jvspatial -d jvspatial -f /docker-entrypoint-initdb.d/01-extensions.sql
```

## Stop / reset

```bash
docker compose stop          # stop, keep data
docker compose down          # stop + remove container, keep volume
docker compose down -v       # WIPE data volume — irreversible
```

## Notes

- Data persists in named volume `jvspatial-pgdata`.
- Slow query log threshold: 500ms.
- Credentials are dev-only; do NOT reuse in any shared/staging env.
