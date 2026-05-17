# CLAUDE.md — Agent Guide for jvspatial

> This file is read automatically by Claude Code at the start of every session in this repo. It is the **canonical entry point** for any AI agent maintaining `jvspatial`. Keep it short, current, and actionable.

---

## What jvspatial is

`jvspatial` is an **async-first, serverless-compatible, object-spatial Python library** for graph-based persistence and business-logic layers. It layers an entity-centric graph model (Object → Node / Edge / Walker / Root) over four database backends (JSON, SQLite, MongoDB, DynamoDB), and ships a FastAPI integration with auth, file storage, observability, and serverless ergonomics.

For full positioning and non-goals, read [PRD.md](PRD.md).
For the technical contract, read [SPEC.md](SPEC.md).

---

## Where to look first

When given a task, resolve context in this order:

1. **[PRD.md](PRD.md)** — what's the product context? Is this in scope?
2. **[SPEC.md](SPEC.md)** — what does the library currently guarantee about the area you're touching? Every claim cites a `file:line`.
3. **[docs/md/README.md](docs/md/README.md)** — index of how-to docs. Find the relevant one before reading source.
4. **[ROADMAP.md](ROADMAP.md)** — is this area under active hardening? Known gap? Out of scope?
5. **[CHANGELOG.md](CHANGELOG.md)** — recent changes that may affect your work.
6. **Source code** — last, not first. The map of subpackage READMEs (`jvspatial/*/README.md`) shortens this hop.

If a doc disagrees with code, the doc is wrong. File an issue and trust the code — but cite the discrepancy.

---

## Non-negotiable invariants

These are properties the library guarantees. Breaking them is a regression even if tests pass.

### 1. Async-only I/O

Every database call, network call, and file-system call is `async`. There are **no sync wrappers** in the library. Sync is for pure computation only.

- ❌ `entity.save()` (missing `await`)
- ✅ `await entity.save()`

If you find yourself wanting a sync wrapper, you are solving the wrong problem.

### 2. Constant-time secret comparison

Any comparison of a secret, key, token, or password hash uses `hmac.compare_digest`. Affected paths (SPEC §15.2):
- API key verification, refresh token comparison, password reset token, webhook HMAC, deferred-invoke secret, bcrypt legacy fallback.

Never replace `hmac.compare_digest` with `==` for performance or readability.

### 3. Entity name override (`__entity_name__`)

Persisted entity discriminator is `cls.__dict__.get("__entity_name__") or cls.__name__` (SPEC §1.2). Resolution is **per-subclass**, not inherited. Code that constructs IDs or looks up subclasses must go through `generate_id()` and `find_subclass_by_name()` — never assemble IDs from `cls.__name__` directly.

### 4. Serverless detection precedence

`is_serverless_mode(config=None)` resolves: explicit config → current Server config → `SERVERLESS_MODE` env → auto-detection (SPEC §11.1). Do not bypass with custom env reads. Do not memoize results across tests — call `reset_serverless_mode_cache()` between cases.

### 5. Protected attribute validation

`Object.__setattr__` validates field names against the class hierarchy. Setting an undeclared attribute on an `Object` is rejected. Never use `object.__setattr__(self, ...)` to bypass; if you need a new field, declare it.

### 6. Deferred-save MRO

`class MyEntity(DeferredSaveMixin, Node)` — mixin must come **before** the base. Wrong order silently disables batching. Tests should assert MRO-sensitive behavior.

### 7. Stability tier discipline

Symbols in `jvspatial.__all__` are public — breaking changes require a deprecation cycle (`docs/md/stability.md`). Underscore-prefixed modules are internal — callers should not import directly. Promoting an internal helper to public is a product decision; update PRD §7 and docs/md/stability.md together.

### 8. CORS / CSP / docs defaults

CORS does **not** default to wildcard. CSP is strict on app routes, relaxed only on `/docs`, `/redoc`, `/openapi.json`. `JVSPATIAL_DOCS_DISABLED` is the production posture. Do not weaken these defaults without a security review entry.

### 9. Walker protection

`max_steps=10000`, `max_visits_per_node=100`, `max_execution_time=300s`, `max_queue_size=1000` are defaults that prevent DOS. Disabling protection is allowed locally; never disable globally or in code that touches user input.

---

## Common gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `TypeError: object NoneType can't be used in 'await' expression` | Forgot `await` on async DB call | Add `await` |
| Custom mixin doesn't batch saves | `DeferredSaveMixin` placed after base in MRO | Mixin first: `class X(DeferredSaveMixin, Node)` |
| Subclass lookup returns wrong class | Two unrelated classes share `__name__` | Set `__entity_name__: ClassVar[Optional[str]] = "Distinct"` on one |
| Tests pass locally, fail under serverless mode | Forgot to test both modes | Use `reset_serverless_mode_cache()` between tests |
| 401 with valid token | Auth state on wrong database | Auth is **always** on prime DB; do not relocate |
| Slow query never logged | `slow_query_ms` not configured | Set in `create_database(observe=True, slow_query_ms=N)` |
| Walker visits the same node forever | Protection disabled | Re-enable `protection_enabled=True` |
| `JVSPATIAL_FOO` env var ignored | Not in allowlist | Add to `jvspatial/env_adapter.py` allowlist |
| SQLite query falls back to in-memory filter | Operator not yet pushed down by `SQLiteTranslator` | Check `jvspatial/db/_sqlite_translate.py` for supported operators |

---

## Run the dev loop

```bash
# install
pip install -e '.[dev,test]'
pre-commit install

# fast feedback
pytest -q                                    # unit + integration (skips benchmarks)
pre-commit run --all-files                   # lint / format / type-check

# full quality bar (run before opening PR)
pytest --cov=jvspatial --cov-report=term-missing

# benchmarks (regression detection)
pytest tests/benchmarks --benchmark-only
```

Async tests use `pytest-asyncio` in auto mode (`pyproject.toml`). No manual marker needed for `async def test_*`.

---

## How to make changes safely

### Add a feature

1. Read [PRD §8](PRD.md#8-decision-boundaries) — does the change pass the decision rules?
2. Read the relevant SPEC section. Does the change alter the contract? If yes, plan a SPEC update in the same commit.
3. Test-first on the **JSON backend** — fastest iteration, no external dependencies.
4. Check stability tier of the file you're touching ([docs/md/stability.md](docs/md/stability.md)).
5. Update [CHANGELOG.md](CHANGELOG.md) under `## [Unreleased]`.
6. If touching a public name, also update `jvspatial.__all__`.

### Fix a bug

1. Reproduce in a failing test.
2. Resolve root cause; do not paper over.
3. If the bug reveals a SPEC inaccuracy, update SPEC.
4. CHANGELOG entry under `### Fixed`.

### Touch auth, secrets, or security

1. Read [docs/md/security-review.md](docs/md/security-review.md) and [docs/md/security-operational-notes.md](docs/md/security-operational-notes.md).
2. Preserve constant-time comparisons.
3. Add a corresponding security-review entry for the change.

### Touch a serverless code path

1. Check `is_serverless_mode()` precedence (SPEC §11.1) before adding new mode-sensitive defaults.
2. Test both modes; reset the detection cache between tests.
3. If adding a Lambda-specific behavior, document the LWA interaction in [docs/md/serverless-mode.md](docs/md/serverless-mode.md).

### Add a database backend

1. Subclass `Database` (`jvspatial/db/database.py:48`).
2. Register via `register_database_type("name", factory_fn)` (`jvspatial/db/factory.py`).
3. Implement bulk overrides (`find_many`, `bulk_save`); the defaults are correct but slow.
4. Set `supports_transactions` capability flag.
5. Add backend-specific tests in `tests/db/`.

---

## Boundaries — what NOT to do

- Do **not** add a sync version of any I/O API.
- Do **not** broaden CORS defaults to wildcards.
- Do **not** replace `hmac.compare_digest` with `==`.
- Do **not** commit `.env` or any secrets. Use `.env.example` for templates.
- Do **not** import from underscore-prefixed modules (`_atomic`, `_path_locks`, `_cache`, `_observable`) — go through the public factory.
- Do **not** modify SPEC.md without modifying the corresponding code in the same commit (or vice versa).
- Do **not** edit `LLM-CODING-GUIDE.md` — it is preserved as a legacy reference. New documentation belongs in `docs/md/` or in PRD/SPEC/ROADMAP.
- Do **not** add features mentioning specific downstream consumers in the library or its docs. jvspatial is a foundation; consumer-specific logic lives downstream.

---

## Repo geography

```
jvspatial/
├── core/              # Entity hierarchy, GraphContext, events
│   ├── entities/      # Object, Node, Edge, Walker, Root
│   ├── annotations/   # @attribute system
│   └── walker_components/ # Trail, protection, queue, events
├── api/               # FastAPI integration
│   ├── auth/          # JWT, API keys, RBAC, sessions
│   ├── components/    # AppBuilder, AuthConfigurator, middleware
│   ├── decorators/    # @endpoint
│   ├── endpoints/     # Registry, factory, router
│   └── integrations/  # Webhooks, scheduler, storage service
├── db/                # Database backends + abstraction
│   ├── jsondb.py, sqlite.py, mongodb.py, dynamodb.py
│   ├── _atomic.py, _path_locks.py, _cache.py, _observable.py  # internal
│   └── query.py, factory.py, manager.py
├── storage/           # File storage
│   ├── interfaces/    # Local, S3
│   └── security/      # path_sanitizer, validator
├── cache/             # Memory, Redis, layered
├── serverless/        # Deferred task dispatch
├── runtime/           # Serverless detection, LWA helpers
├── observability/     # Metrics, OTEL adapter
├── logging/           # Custom levels, persisted logging
├── exceptions.py      # Central exception hierarchy
├── env.py             # Env helpers
├── env_adapter.py     # JVSPATIAL_* allowlist + merge
└── version.py         # Single source of version truth

tests/                 # Mirrors jvspatial/ layout
docs/md/               # How-to and reference docs (see docs/md/README.md)
examples/              # Runnable example scripts
```

Each top-level subpackage has its own `README.md` (added in this docs pass) — read that before diving into source.

---

## Slash commands and skills relevant in this repo

- `pytest` and `pytest --benchmark-only` are the canonical test entry points.
- `pre-commit run --all-files` runs the full linter/formatter suite (black, isort, flake8, mypy, detect-secrets).
- For larger refactors, follow the [docs/md/contributing.md](docs/md/contributing.md) workflow; for security-sensitive changes, the workflow in [docs/md/security-review.md](docs/md/security-review.md).

---

## Pointers to authoritative sources

When in doubt, the source-of-truth order is:

1. Code (always)
2. [SPEC.md](SPEC.md) (technical contract; should match code)
3. [PRD.md](PRD.md) (product context)
4. [docs/md/](docs/md/) (how-to)
5. [CHANGELOG.md](CHANGELOG.md) (release notes)
6. [LLM-CODING-GUIDE.md](LLM-CODING-GUIDE.md) (legacy; informational only, not contractual)

---

**Last updated**: Same commit as the PRD/SPEC/ROADMAP docs pass. Update this file in the same commit as any change that alters an invariant or boundary above.
