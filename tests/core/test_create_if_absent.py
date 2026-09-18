"""Object.create_if_absent — atomic create-or-return-existing."""

from __future__ import annotations

import tempfile
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import Field

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities import Object
from jvspatial.core.mixins import DeferredSaveMixin
from jvspatial.db.factory import create_database


class Receipt(Object):
    __test__ = False
    name: str = ""
    value: int = 0
    type_code: str = Field(default="o")


class DeferredReceipt(DeferredSaveMixin, Object):
    __test__ = False
    name: str = ""
    value: int = 0
    type_code: str = Field(default="o")


@pytest.fixture
def temp_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        import uuid

        path = f"{tmpdir}/cif_{uuid.uuid4().hex}"
        database = create_database("json", base_path=path)
        context = GraphContext(database=database)
        set_default_context(context)
        yield context


@pytest.mark.asyncio
async def test_create_if_absent_inserts_then_returns_existing(temp_context):
    fixed_id = "o.Receipt.deadbeefcafebabe"
    a, created_a = await Receipt.create_if_absent(id=fixed_id, name="first", value=1)
    assert created_a is True
    assert a.id == fixed_id
    assert a.name == "first"
    assert a.value == 1

    b, created_b = await Receipt.create_if_absent(id=fixed_id, name="second", value=999)
    assert created_b is False
    assert b.id == fixed_id
    assert b.name == "first"
    assert b.value == 1  # rehydrated from stored, not proposed


@pytest.mark.asyncio
async def test_create_if_absent_does_not_call_save(temp_context):
    fixed_id = "o.Receipt.nosave00000001"
    with patch.object(Receipt, "save", new_callable=AsyncMock) as mock_save:
        entity, created = await Receipt.create_if_absent(id=fixed_id, name="x", value=2)
        assert created is True
        assert entity.name == "x"
        mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_create_if_absent_auto_id_always_creates(temp_context):
    a, ca = await Receipt.create_if_absent(name="a", value=1)
    b, cb = await Receipt.create_if_absent(name="b", value=2)
    assert ca is True and cb is True
    assert a.id != b.id


@pytest.mark.asyncio
async def test_deferred_flush_only_when_created(temp_context, monkeypatch):
    monkeypatch.setenv("SERVERLESS_MODE", "false")
    monkeypatch.setenv("JVSPATIAL_ENABLE_DEFERRED_SAVES", "true")
    from jvspatial.runtime.serverless import reset_serverless_mode_cache

    reset_serverless_mode_cache()

    fixed_id = "o.DeferredReceipt.aabbccddeeff0011"
    flushes: list[str] = []

    original_flush = DeferredReceipt.flush

    async def tracking_flush(self: Any) -> None:
        flushes.append(self.id)
        await original_flush(self)

    with patch.object(DeferredReceipt, "flush", tracking_flush):
        e1, c1 = await DeferredReceipt.create_if_absent(
            id=fixed_id, name="one", value=1
        )
        assert c1 is True
        assert flushes == [fixed_id]

        e2, c2 = await DeferredReceipt.create_if_absent(
            id=fixed_id, name="two", value=2
        )
        assert c2 is False
        assert e2.value == 1
        assert flushes == [fixed_id]  # no second flush


@pytest.mark.asyncio
async def test_create_if_absent_attaches_graph_context(temp_context):
    entity, _ = await Receipt.create_if_absent(name="ctx", value=0)
    assert entity._graph_context is temp_context
