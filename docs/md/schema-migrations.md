# Schema migrations

Adding, renaming, or removing a field on an `Object` subclass changes the
on-disk shape of every persisted record. jvspatial's schema-migration
framework upgrades legacy records in place — on read, on demand, or via
the `jvspatial migrate` CLI for a controlled bulk apply.

This closes ROADMAP §2.1: schema migrations are no longer manual.

## Mental model

Every `Object` subclass carries a `__schema_version__: ClassVar[int]`
that starts at `1`. Each persisted record carries the corresponding
version under the `_v` key. When a record is loaded:

1. The framework compares `record["_v"]` (or `1` if absent) to
   `cls.__schema_version__`.
2. If they match, the load proceeds unchanged.
3. If `record["_v"] < cls.__schema_version__`, the framework walks
   the registered migration chain and upgrades the dict before
   hydration.
4. If `record["_v"] > cls.__schema_version__`, the load logs an error
   and continues with the as-stored values — we never downgrade silently.

Migrations are pure functions: `(dict) -> dict`. They get the raw
persisted record (with its `entity` / `context` / `edges` / etc. shape)
and return the upgraded record. The framework handles `_v` stamping
itself.

## Authoring a migration

```python
from typing import ClassVar
from jvspatial import Node
from jvspatial.core.migrations import migration


class User(Node):
    # Bump the version when you change the on-disk shape.
    __schema_version__: ClassVar[int] = 2

    name: str = ""
    email: str = ""   # renamed from "email_address" in v2


@migration(User, from_version=1, to_version=2)
def add_email(record):
    ctx = record.setdefault("context", {})
    if "email_address" in ctx:
        ctx["email"] = ctx.pop("email_address")
    return record
```

That's it. Subsequent `User.get(...)` / `User.find(...)` calls hydrate
the new `email` field even from legacy `email_address` records.

### Multi-step chains

Each `@migration` call defines one step. To go from v1 to v3 you
register two steps (v1→v2 and v2→v3); the framework walks them in
order:

```python
class User(Node):
    __schema_version__: ClassVar[int] = 3
    name: str = ""
    email: str = ""
    display_name: str = ""


@migration(User, from_version=1, to_version=2)
def add_email(record):
    ctx = record.setdefault("context", {})
    if "email_address" in ctx:
        ctx["email"] = ctx.pop("email_address")
    return record


@migration(User, from_version=2, to_version=3)
def populate_display_name(record):
    ctx = record.setdefault("context", {})
    ctx["display_name"] = ctx.get("email", "unknown").split("@")[0]
    return record
```

### Migrations on parents apply to children

The resolver walks the MRO, so a migration registered on `Node` would
apply to every `Node` subclass. Subclasses can override by registering
their own migration for the same version pair.

## Persistence policy

By default, **load-path migration is in-memory only**. The next save
on the upgraded record writes the new shape back to disk; otherwise
the record stays in its v1 form. This is the safest default — reads
don't write.

To opt into write-back on every read:

```python
from jvspatial.core.context import GraphContext

ctx = GraphContext(database=db, auto_persist_migrations=True)
```

With this flag, every successful load-path migration re-saves the
record. Failed write-backs log a warning but do not fail the read.

## Bulk apply via CLI

For controlled rollouts, use the `jvspatial migrate` command:

```bash
# Dry run (default). Reports what would change.
jvspatial migrate --collection node --entity User --import-module myapp.models

# Apply for real.
jvspatial migrate --collection node --entity User --import-module myapp.models --apply

# Migrate every entity in a collection that has registered migrations.
jvspatial migrate --collection node --import-module myapp.models --apply
```

Flags:

| Flag                 | Purpose                                                |
| -------------------- | ------------------------------------------------------ |
| `--collection`       | Required. `"node"` / `"edge"` / `"object"` / `"walker"` |
| `--entity NAME`      | Restrict to a single entity. Default: all entities in the collection that have registered migrations |
| `--import-module M`  | Repeatable. Dotted paths to import before scanning. Use this so the registry sees your `@migration` decorators |
| `--dry-run`          | Default — report only                                  |
| `--apply`            | Actually persist                                       |
| `-v` / `--verbose`   | DEBUG logging                                          |

The CLI uses the prime database from `DatabaseManager`. Configure it
the same way as your application (env vars, etc.).

## Failure modes & how the framework handles them

| Situation                                  | Behavior                                                       |
| ------------------------------------------ | -------------------------------------------------------------- |
| `record["_v"]` absent                      | Treated as version `1` (the legacy default)                    |
| `record["_v"] == cls.__schema_version__`   | No-op                                                          |
| `record["_v"] < cls.__schema_version__`    | Migration chain runs                                           |
| `record["_v"] > cls.__schema_version__`    | `MigrationError` raised; load path logs ERROR and continues with the as-stored record |
| Missing chain step                         | `MigrationError` with the specific missing version pair        |
| Migration step returns non-dict            | `MigrationError`                                               |
| Duplicate `(class, from, to)` registration | `MigrationError` at registration time (fail-fast)              |

## Testing migrations

```python
from jvspatial.core.migrations import apply_migrations

def test_user_v1_to_v2_renames_email():
    legacy = {
        "id": "u.1",
        "entity": "User",
        "context": {"name": "Alice", "email_address": "alice@x.com"},
    }
    upgraded, changed = apply_migrations(legacy, User)
    assert changed
    assert upgraded["context"]["email"] == "alice@x.com"
    assert "email_address" not in upgraded["context"]
    assert upgraded["_v"] == 2
```

For tests that need to register migrations transiently without polluting
the global registry, use the snapshot helpers:

```python
import pytest
from jvspatial.core.migrations import registry

@pytest.fixture(autouse=True)
def _isolate_registry():
    snap = registry.snapshot()
    registry.clear()
    yield
    registry.restore(snap)
```

The jvspatial test suite ships with this exact pattern in
`tests/core/test_migrations.py`.

## See also

- [postgres-guide.md](postgres-guide.md) — for Postgres-backed deployments;
  schema migrations work uniformly across all backends but the cost of
  bulk-applying is lowest on Postgres / MongoDB.
- ROADMAP §2.1 — original gap that this framework closes.
