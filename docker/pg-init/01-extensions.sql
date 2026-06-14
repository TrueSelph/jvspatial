-- Enable extensions jvspatial apps may use.
-- Runs once on first volume init. Re-run via: docker exec jvspatial-pg psql -U jvspatial -d jvspatial -f /docker-entrypoint-initdb.d/01-extensions.sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
