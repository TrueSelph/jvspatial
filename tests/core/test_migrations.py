"""Tests for the schema migration framework.

Covers:

* Registry — registration / chain resolution / duplicate rejection /
  downgrade refusal / missing-step diagnostic.
* MRO walking — a migration on a parent class applies to a child.
* :func:`apply_migrations` legacy-record handling (no ``_v`` key).
* GraphContext load-path migration + auto_persist_migrations.
* CLI ``migrate`` subcommand (dry-run + apply).
"""

from __future__ import annotations

import tempfile
from typing import AsyncIterator, Iterator

import pytest

from jvspatial.core.context import GraphContext
from jvspatial.core.entities.node import Node
from jvspatial.core.entities.object import Object
from jvspatial.core.migrations import (
    LEGACY_VERSION,
    SCHEMA_VERSION_KEY,
    MigrationError,
    apply_migrations,
    migration,
    needs_migration,
    registry,
)
from jvspatial.db.jsondb import JsonDB

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _isolate_registry() -> Iterator[None]:
    """Snapshot + restore the global migration registry around each test."""
    snap = registry.snapshot()
    registry.clear()
    yield
    registry.restore(snap)


# ---- registry --------------------------------------------------------------


class TestRegistry:
    def test_register_and_resolve_single_step(self) -> None:
        class T:
            __schema_version__ = 2

        @migration(T, from_version=1, to_version=2)
        def step(rec):
            rec["upgraded"] = True
            return rec

        chain = registry.get_chain(T, 1, 2)
        assert chain == [step]

    def test_register_and_resolve_multi_step(self) -> None:
        class T:
            __schema_version__ = 3

        @migration(T, from_version=1, to_version=2)
        def s12(rec):
            return rec

        @migration(T, from_version=2, to_version=3)
        def s23(rec):
            return rec

        chain = registry.get_chain(T, 1, 3)
        assert chain == [s12, s23]

    def test_duplicate_registration_raises(self) -> None:
        class T:
            __schema_version__ = 2

        @migration(T, from_version=1, to_version=2)
        def first(rec):
            return rec

        with pytest.raises(MigrationError, match="duplicate"):

            @migration(T, from_version=1, to_version=2)
            def second(rec):
                return rec

    def test_register_rejects_reverse_pair(self) -> None:
        class T:
            __schema_version__ = 2

        with pytest.raises(MigrationError, match="from_version"):

            @migration(T, from_version=3, to_version=2)
            def bad(rec):
                return rec

    def test_missing_step_diagnostic(self) -> None:
        class T:
            __schema_version__ = 3

        @migration(T, from_version=1, to_version=2)
        def s12(rec):
            return rec

        # No 2 -> 3 registration; chain should fail with a specific
        # diagnostic naming the missing step.
        with pytest.raises(MigrationError, match="version 2 -> 3"):
            registry.get_chain(T, 1, 3)

    def test_downgrade_refused(self) -> None:
        class T:
            __schema_version__ = 1

        with pytest.raises(MigrationError, match="downgrade"):
            registry.get_chain(T, 5, 1)

    def test_mro_inheritance(self) -> None:
        """A migration on a parent class applies to subclasses."""

        class Base:
            __schema_version__ = 2

        @migration(Base, from_version=1, to_version=2)
        def stamp(rec):
            rec["from_base"] = True
            return rec

        class Child(Base):
            __schema_version__ = 2

        chain = registry.get_chain(Child, 1, 2)
        assert chain == [stamp]

    def test_subclass_override_wins(self) -> None:
        """A subclass migration overrides the parent's for the same version step."""

        class Base:
            __schema_version__ = 2

        @migration(Base, from_version=1, to_version=2)
        def base_step(rec):
            rec["who"] = "base"
            return rec

        class Child(Base):
            __schema_version__ = 2

        @migration(Child, from_version=1, to_version=2)
        def child_step(rec):
            rec["who"] = "child"
            return rec

        chain = registry.get_chain(Child, 1, 2)
        assert chain == [child_step]


# ---- apply_migrations ------------------------------------------------------


class TestApplyMigrations:
    def test_legacy_record_treated_as_v1(self) -> None:
        class T:
            __schema_version__ = 2

        @migration(T, from_version=1, to_version=2)
        def s(rec):
            rec["upgraded"] = True
            return rec

        # No ``_v`` key → treated as legacy (v1).
        out, changed = apply_migrations({"id": "x"}, T)
        assert changed
        assert out["upgraded"] is True
        assert out[SCHEMA_VERSION_KEY] == 2

    def test_noop_when_already_current(self) -> None:
        class T:
            __schema_version__ = 1

        out, changed = apply_migrations({"id": "x", "_v": 1}, T)
        assert not changed

    def test_returns_dict_with_target_version(self) -> None:
        class T:
            __schema_version__ = 3

        @migration(T, from_version=1, to_version=2)
        def s12(rec):
            rec["s12"] = True
            return rec

        @migration(T, from_version=2, to_version=3)
        def s23(rec):
            rec["s23"] = True
            return rec

        out, changed = apply_migrations({"id": "x"}, T)
        assert changed
        assert out["s12"] is True
        assert out["s23"] is True
        assert out[SCHEMA_VERSION_KEY] == 3

    def test_step_returning_non_dict_raises(self) -> None:
        class T:
            __schema_version__ = 2

        @migration(T, from_version=1, to_version=2)
        def bad(_rec):
            return "not a dict"  # type: ignore[return-value]

        with pytest.raises(MigrationError, match="returned"):
            apply_migrations({"id": "x"}, T)

    def test_needs_migration_true_for_legacy(self) -> None:
        class T:
            __schema_version__ = 2

        assert needs_migration({"id": "x"}, T) is True

    def test_needs_migration_false_for_current(self) -> None:
        class T:
            __schema_version__ = 1

        assert needs_migration({"id": "x", "_v": 1}, T) is False


# ---- GraphContext load-path integration ------------------------------------


@pytest.fixture
async def ctx_jsondb() -> AsyncIterator[GraphContext]:
    with tempfile.TemporaryDirectory() as tmp:
        yield GraphContext(database=JsonDB(base_path=tmp))


class _UserV2(Node):
    """Migration-tested subclass; isolated from the global User namespace
    so other tests don't see it."""

    __schema_version__ = 2
    name: str = ""
    email: str = ""


@migration(_UserV2, from_version=1, to_version=2)
def _user_v1_to_v2(record):
    ctx = record.setdefault("context", {})
    if "email_address" in ctx:
        ctx["email"] = ctx.pop("email_address")
    return record


class TestLoadPathMigration:
    async def test_legacy_record_upgrades_in_memory(
        self, ctx_jsondb: GraphContext
    ) -> None:
        # Re-register the test-local migration since registry was wiped
        # by the autouse fixture.
        from jvspatial.core.migrations import registry as _reg

        _reg.register(_UserV2, 1, 2, _user_v1_to_v2)

        legacy = {
            "id": "n.UserV2.legacy",
            "entity": "_UserV2",
            "context": {"name": "Alice", "email_address": "alice@example.com"},
            "edges": [],
        }
        await ctx_jsondb.database.save("node", legacy)

        loaded = await ctx_jsondb.get(_UserV2, "n.UserV2.legacy")
        assert loaded is not None
        assert loaded.name == "Alice"
        assert loaded.email == "alice@example.com"

        # Without auto_persist, disk record is unchanged.
        disk = await ctx_jsondb.database.get("node", "n.UserV2.legacy")
        assert SCHEMA_VERSION_KEY not in disk
        assert "email_address" in disk["context"]

    async def test_auto_persist_rewrites_disk(self) -> None:
        from jvspatial.core.migrations import registry as _reg

        _reg.register(_UserV2, 1, 2, _user_v1_to_v2)

        with tempfile.TemporaryDirectory() as tmp:
            db = JsonDB(base_path=tmp)
            legacy = {
                "id": "n.UserV2.legacy",
                "entity": "_UserV2",
                "context": {"name": "Bob", "email_address": "b@x.com"},
                "edges": [],
            }
            await db.save("node", legacy)

            ctx = GraphContext(database=db, auto_persist_migrations=True)
            loaded = await ctx.get(_UserV2, "n.UserV2.legacy")
            assert loaded is not None

            disk = await db.get("node", "n.UserV2.legacy")
            assert disk[SCHEMA_VERSION_KEY] == 2
            assert disk["context"]["email"] == "b@x.com"
            assert "email_address" not in disk["context"]

    async def test_missing_migration_logged_not_raised(
        self, ctx_jsondb: GraphContext, caplog
    ) -> None:
        """Records that can't be migrated stay accessible — better to
        deliver the data and log than to break reads."""

        class _Broken(Node):
            __schema_version__ = 5
            name: str = ""

        legacy = {
            "id": "n.Broken.1",
            "entity": "_Broken",
            "context": {"name": "x"},
            "edges": [],
        }
        await ctx_jsondb.database.save("node", legacy)

        import logging

        with caplog.at_level(logging.ERROR):
            loaded = await ctx_jsondb.get(_Broken, "n.Broken.1")
        # Load still succeeds with the as-stored values.
        assert loaded is not None
        # Error was logged.
        assert any("Skipping migration" in r.message for r in caplog.records)


# ---- CLI -------------------------------------------------------------------


class _Account(Node):
    __schema_version__ = 2
    name: str = ""
    plan: str = ""


@migration(_Account, from_version=1, to_version=2)
def _account_v1_to_v2(record):
    ctx = record.setdefault("context", {})
    if "tier" in ctx:
        ctx["plan"] = ctx.pop("tier")
    return record


class TestCLIMigrate:
    @pytest.fixture
    async def cli_db(self) -> AsyncIterator[JsonDB]:
        with tempfile.TemporaryDirectory() as tmp:
            db = JsonDB(base_path=tmp)
            for i, tier in enumerate(["free", "pro", "enterprise"]):
                await db.save(
                    "node",
                    {
                        "id": f"n.Account.{i}",
                        "entity": "_Account",
                        "context": {"name": f"acct-{i}", "tier": tier},
                        "edges": [],
                    },
                )
            yield db

    async def test_dry_run_does_not_persist(
        self, cli_db: JsonDB, monkeypatch, caplog
    ) -> None:
        # Re-register migration after the registry-isolation fixture
        # cleared it.
        from jvspatial.core.migrations import registry as _reg

        _reg.register(_Account, 1, 2, _account_v1_to_v2)

        # Wire the test db into the manager so the CLI uses it.
        # Patch get_database_manager so the CLI sees a fresh manager
        # bound to cli_db as the prime database (not the process-wide
        # singleton, which may carry state from other tests).
        class _StubManager:
            def get_prime_database(self):
                return cli_db

        monkeypatch.setattr(
            "jvspatial.db.manager.get_database_manager",
            lambda: _StubManager(),
        )
        monkeypatch.setattr(
            "jvspatial.cli.get_database_manager",
            lambda: _StubManager(),
            raising=False,
        )

        import logging

        from jvspatial.cli import _run_migrate, build_parser

        parser = build_parser()
        args = parser.parse_args(
            ["migrate", "--collection", "node", "--entity", "_Account"]
        )
        with caplog.at_level(logging.INFO):
            rc = await _run_migrate(args)
        assert rc == 0

        # Records unchanged on disk.
        for i in range(3):
            disk = await cli_db.get("node", f"n.Account.{i}")
            assert "tier" in disk["context"]
            assert SCHEMA_VERSION_KEY not in disk

        assert any("dry-run" in m.lower() for m in caplog.messages)

    async def test_apply_persists(self, cli_db: JsonDB, monkeypatch) -> None:
        from jvspatial.core.migrations import registry as _reg

        _reg.register(_Account, 1, 2, _account_v1_to_v2)

        # Sanity: confirm the fixture's db is what we think it is.
        seeded = await cli_db.find("node", {})
        assert len(seeded) == 3, (
            f"fixture seeded {len(seeded)} records " f"(base_path={cli_db.base_path})"
        )

        class _StubManager:
            def get_prime_database(self):
                return cli_db

        monkeypatch.setattr(
            "jvspatial.db.manager.get_database_manager",
            lambda: _StubManager(),
        )

        from jvspatial.cli import _run_migrate, build_parser

        parser = build_parser()
        args = parser.parse_args(
            ["migrate", "--collection", "node", "--entity", "_Account", "--apply"]
        )
        rc = await _run_migrate(args)
        assert rc == 0

        for i in range(3):
            disk = await cli_db.get("node", f"n.Account.{i}")
            assert disk[SCHEMA_VERSION_KEY] == 2
            assert "plan" in disk["context"]
            assert "tier" not in disk["context"]
