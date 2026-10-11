# Object.create_if_absent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship portable atomic `Database.insert_if_absent` + `Object.create_if_absent` without changing upsert `save()`.

**Architecture:** New ABC result type + method; each adapter implements insert-or-return-existing on primary `id`; Object layer exports, calls DB, rehydrates on conflict. Never route through `save()`.

**Tech Stack:** Python 3.9+, aiosqlite, asyncpg, motor, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-09-18-create-if-absent-design.md`

---

### Task 1: ABC + SQLite + Object + tests

**Files:**
- Modify: `jvspatial/db/database.py`
- Modify: `jvspatial/db/sqlite.py`
- Modify: `jvspatial/core/entities/object.py`
- Modify: `jvspatial/core/context.py` (if needed for cache)
- Create: `tests/core/test_object_create_if_absent.py`
- Create: `tests/db/test_sqlite_insert_if_absent.py`

- [ ] RED/GREEN Object + SQLite concurrent same-id
- [ ] Commit

### Task 2: Postgres, Mongo, JsonDB, DynamoDB, wrappers

**Files:**
- Modify: `jvspatial/db/postgres.py` (+ transaction save path if separate)
- Modify: `jvspatial/db/mongodb.py`
- Modify: `jvspatial/db/jsondb.py`
- Modify: `jvspatial/db/dynamodb.py` (if present)
- Modify: `jvspatial/db/_cache.py`, `jvspatial/db/_observable.py`
- Extend integration tests

- [ ] RED/GREEN per adapter
- [ ] Commit

### Task 3: Docs, version, changelog, stability, PR

**Files:**
- Modify: `CHANGELOG.md`, `jvspatial/version.py`, `docs/md/stability.md`, `docs/md/entity-reference.md`, `SPEC.md` if needed
- Export `__all__`

- [ ] Docs + 0.0.20 bump
- [ ] Push + `gh pr create`
