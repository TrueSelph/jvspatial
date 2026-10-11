"""SQLite partial unique indexes — Conversation/Interaction session_id fix.

A global UNIQUE on ``context.session_id`` makes ``INSERT OR REPLACE`` wipe
Interaction rows when Conversation shares the same session_id. Partial
filters (same dialect as Postgres) must scope uniqueness.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import pytest

from jvspatial.core.annotations import attribute, compound_index
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities import Node
from jvspatial.db import create_database

try:
    from jvspatial.db.sqlite import SQLiteDB

    HAS_SQLITE = True
except ImportError:  # pragma: no cover
    SQLiteDB = None  # type: ignore[misc]
    HAS_SQLITE = False

pytestmark = pytest.mark.skipif(
    not HAS_SQLITE, reason="aiosqlite is required for SQLite tests"
)


@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir) / "partial.db"


@pytest.fixture
async def sqlite_db(temp_db_path):
    db = create_database("sqlite", db_path=str(temp_db_path))
    try:
        yield db
    finally:
        if hasattr(db, "close"):
            await db.close()


@pytest.fixture
async def sqlite_context(sqlite_db):
    ctx = GraphContext(database=sqlite_db)
    set_default_context(ctx)
    return ctx


@compound_index(
    [("session_id", 1)],
    name="conversation_session_id",
    unique=True,
    partial_filter_expression={
        "context.session_id": {"$gt": ""},
        "context.status": {"$gt": ""},
    },
)
class ConversationLike(Node):
    __test__ = False
    session_id: str = attribute(default="")
    status: str = attribute(default="active")


class InteractionLike(Node):
    __test__ = False
    session_id: str = attribute(default="")
    conversation_id: str = attribute(default="")
    utterance: str = attribute(default="")


async def _index_sql(db: SQLiteDB, name: str) -> Optional[str]:
    conn = await db._get_connection()
    cursor = await conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    )
    row = await cursor.fetchone()
    return row[0] if row else None


@pytest.mark.asyncio
async def test_partial_unique_allows_interaction_same_session_id(
    sqlite_context, sqlite_db
):
    """Conversation + Interaction can share session_id; both rows persist."""
    # Call create_index on this DB directly — GraphContext.ensure_indexes is
    # process-cached per class and would skip on later temp databases.
    await sqlite_db.create_index(
        "node",
        "context.session_id",
        unique=True,
        partialFilterExpression={
            "context.session_id": {"$gt": ""},
            "context.status": {"$gt": ""},
        },
    )

    conv = await ConversationLike.create(session_id="sess_shared", status="active")
    ix = await InteractionLike.create(
        session_id="sess_shared",
        conversation_id=conv.id,
        utterance="hello",
    )

    assert await ConversationLike.get(conv.id) is not None
    assert await InteractionLike.get(ix.id) is not None

    # Re-save conversation (the wipe path under a global unique index)
    conv.status = "active"
    await conv.save()

    conn = await sqlite_db._get_connection()
    cursor = await conn.execute(
        "SELECT id FROM records WHERE collection='node' AND id=?",
        (ix.id,),
    )
    assert await cursor.fetchone() is not None
    cursor = await conn.execute(
        "SELECT id FROM records WHERE collection='node' AND id=?",
        (conv.id,),
    )
    assert await cursor.fetchone() is not None


@pytest.mark.asyncio
async def test_partial_unique_still_enforced_within_conversation_set(
    sqlite_context, sqlite_db
):
    """Two Conversation-like rows with same session_id still collide."""
    await sqlite_db.create_index(
        "node",
        "context.session_id",
        unique=True,
        partialFilterExpression={
            "context.session_id": {"$gt": ""},
            "context.status": {"$gt": ""},
        },
    )

    index_sql = await _index_sql(sqlite_db, "idx_node_context_session_id")
    assert index_sql is not None
    assert "UNIQUE" in index_sql.upper()
    assert "WHERE" in index_sql.upper()

    first = await ConversationLike.create(session_id="sess_dup", status="active")
    second = ConversationLike(session_id="sess_dup", status="active")
    await second.save()

    # INSERT OR REPLACE on unique conflict: only one row for that session_id
    conn = await sqlite_db._get_connection()
    cursor = await conn.execute(
        """
        SELECT id FROM records
        WHERE collection = 'node'
          AND json_extract(data, '$.context.session_id') = ?
          AND json_extract(data, '$.entity') = 'ConversationLike'
        """,
        ("sess_dup",),
    )
    ids = [row[0] for row in await cursor.fetchall()]
    assert ids == [second.id]
    assert first.id not in ids


@pytest.mark.asyncio
async def test_create_index_emits_where_clause(sqlite_db):
    await sqlite_db.create_index(
        "node",
        "context.session_id",
        unique=True,
        partialFilterExpression={
            "context.session_id": {"$gt": ""},
            "context.status": {"$gt": ""},
        },
    )
    sql = await _index_sql(sqlite_db, "idx_node_context_session_id")
    assert sql is not None
    assert "WHERE" in sql
    assert "json_extract(data, '$.context.session_id') > ''" in sql
    assert "json_extract(data, '$.context.status') > ''" in sql


@pytest.mark.asyncio
async def test_create_index_repairs_non_partial_unique(sqlite_db):
    # Simulate pre-fix global unique index
    conn = await sqlite_db._get_connection()
    await conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_node_context_session_id
        ON records (collection, json_extract(data, '$.context.session_id'))
        """
    )
    await conn.commit()
    before = await _index_sql(sqlite_db, "idx_node_context_session_id")
    assert before is not None
    assert "WHERE" not in before.upper()

    await sqlite_db.create_index(
        "node",
        "context.session_id",
        unique=True,
        partialFilterExpression={
            "context.session_id": {"$gt": ""},
            "context.status": {"$gt": ""},
        },
    )
    after = await _index_sql(sqlite_db, "idx_node_context_session_id")
    assert after is not None
    assert "WHERE" in after.upper()
    assert "json_extract(data, '$.context.status') > ''" in after


@pytest.mark.asyncio
async def test_create_index_raises_on_untranslatable_partial(sqlite_db):
    with pytest.raises(ValueError, match="cannot translate"):
        await sqlite_db.create_index(
            "node",
            "context.name",
            unique=True,
            partialFilterExpression={"context.name": {"$regex": "^x"}},
        )


@pytest.mark.asyncio
async def test_connect_time_drops_non_partial_session_id_unique(temp_db_path):
    """Opening a DB drops a legacy global session_id unique index."""
    # Seed with the bad index using a first connection, then close.
    seed = create_database("sqlite", db_path=str(temp_db_path))
    conn = await seed._get_connection()
    await conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_node_context_session_id
        ON records (collection, json_extract(data, '$.context.session_id'))
        """
    )
    await conn.commit()
    before = await _index_sql(seed, "idx_node_context_session_id")
    assert before is not None
    assert "WHERE" not in before.upper()
    await seed.close()

    # Fresh open must drop the non-partial unique index on connect.
    db = create_database("sqlite", db_path=str(temp_db_path))
    try:
        await db._get_connection()
        after_connect = await _index_sql(db, "idx_node_context_session_id")
        assert after_connect is None

        ctx = GraphContext(database=db)
        set_default_context(ctx)

        await db.create_index(
            "node",
            "context.session_id",
            unique=True,
            partialFilterExpression={
                "context.session_id": {"$gt": ""},
                "context.status": {"$gt": ""},
            },
        )
        rebuilt = await _index_sql(db, "idx_node_context_session_id")
        assert rebuilt is not None
        assert "WHERE" in rebuilt.upper()

        conv = await ConversationLike.create(session_id="sess_connect", status="active")
        ix = await InteractionLike.create(
            session_id="sess_connect",
            conversation_id=conv.id,
            utterance="ping",
        )
        conv.status = "active"
        await conv.save()

        conn2 = await db._get_connection()
        for entity_id in (conv.id, ix.id):
            cursor = await conn2.execute(
                "SELECT id FROM records WHERE collection='node' AND id=?",
                (entity_id,),
            )
            assert await cursor.fetchone() is not None
    finally:
        await db.close()


def test_is_non_partial_session_id_unique_index_helper():
    assert (
        SQLiteDB._is_non_partial_session_id_unique_index(
            "CREATE UNIQUE INDEX idx_node_context_session_id "
            "ON records (collection, json_extract(data, '$.context.session_id'))"
        )
        is True
    )
    assert (
        SQLiteDB._is_non_partial_session_id_unique_index(
            "CREATE UNIQUE INDEX idx_node_context_session_id "
            "ON records (collection, json_extract(data, '$.context.session_id')) "
            "WHERE json_extract(data, '$.context.status') > ''"
        )
        is False
    )
    assert (
        SQLiteDB._is_non_partial_session_id_unique_index(
            "CREATE INDEX idx_node_context_session_id "
            "ON records (collection, json_extract(data, '$.context.session_id'))"
        )
        is False
    )
