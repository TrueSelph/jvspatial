"""Object.create flushes DeferredSaveMixin instances so get(id) works immediately."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities import Node
from jvspatial.core.mixins import DeferredSaveMixin
from jvspatial.db import create_database
from jvspatial.env import clear_load_env_cache
from jvspatial.runtime.serverless import reset_serverless_mode_cache

try:
    from jvspatial.db.sqlite import SQLiteDB  # noqa: F401

    HAS_SQLITE = True
except ImportError:  # pragma: no cover
    HAS_SQLITE = False

pytestmark = pytest.mark.skipif(
    not HAS_SQLITE, reason="aiosqlite is required for SQLite-backed GraphContext"
)


class _DeferredTestNode(DeferredSaveMixin, Node):
    """Node with deferred saves, mirroring jvagent Conversation / Interaction MRO."""

    __test__ = False

    name: str = ""
    value: int = 0


@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir) / "test.db"


@pytest.fixture
async def sqlite_context(temp_db_path):
    db = create_database("sqlite", db_path=str(temp_db_path))
    ctx = GraphContext(database=db)
    set_default_context(ctx)
    try:
        yield ctx
    finally:
        if hasattr(db, "close"):
            await db.close()


@pytest.fixture(autouse=True)
def _reset_env_caches():
    reset_serverless_mode_cache()
    clear_load_env_cache()
    yield
    reset_serverless_mode_cache()
    clear_load_env_cache()


@pytest.mark.asyncio
async def test_create_deferred_node_visible_to_get_when_deferred_saves_on(
    sqlite_context,
):
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "false", "JVSPATIAL_ENABLE_DEFERRED_SAVES": "true"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        clear_load_env_cache()

        node = await _DeferredTestNode.create(name="first", value=42)
        nid = node.id

        loaded = await _DeferredTestNode.get(nid)
        assert loaded is not None
        assert loaded.name == "first"
        assert loaded.value == 42


@pytest.mark.asyncio
async def test_create_deferred_node_visible_to_get_when_deferred_saves_off(
    sqlite_context,
):
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "false", "JVSPATIAL_ENABLE_DEFERRED_SAVES": "false"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        clear_load_env_cache()

        node = await _DeferredTestNode.create(name="second", value=7)
        nid = node.id

        loaded = await _DeferredTestNode.get(nid)
        assert loaded is not None
        assert loaded.name == "second"
        assert loaded.value == 7
