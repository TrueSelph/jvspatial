"""ObjectPager fixes (audit §8.1, §8.2).

Wave 2 changes:

* Drop the in-memory ``_cache`` entirely — entries were never invalidated
  on writes, so callers got stale rows after any save/delete on the
  underlying collection.
* Reject ``after_id`` combined with ``order_by`` — the cursor only tracks
  ``id`` so a non-id sort key would skip or duplicate rows on writes
  between pages.
"""

import tempfile
import uuid

import pytest

from jvspatial.core.context import GraphContext, scoped_default_context_async
from jvspatial.core.entities import Node
from jvspatial.core.pager import ObjectPager
from jvspatial.db import create_database


class PageNode(Node):
    name: str = ""
    value: int = 0


@pytest.fixture
async def context():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = create_database("json", base_path=f"{tmpdir}/{uuid.uuid4().hex}")
        ctx = GraphContext(database=db)
        async with scoped_default_context_async(ctx):
            yield ctx


def test_object_pager_has_no_cache_attribute():
    """The previously-stale ``_cache`` attribute is gone."""
    pager = ObjectPager(PageNode, page_size=3)
    assert not hasattr(pager, "_cache")


@pytest.mark.asyncio
async def test_after_id_with_order_by_rejected():
    pager = ObjectPager(PageNode, page_size=3, order_by="value")
    with pytest.raises(ValueError, match="after_id"):
        await pager.get_page(after_id="n.PageNode.abc")


@pytest.mark.asyncio
async def test_get_page_no_stale_cache_after_write(context):
    # Seed: 4 nodes.
    nodes = [PageNode(name=f"n{i}", value=i) for i in range(4)]
    for n in nodes:
        await context.save(n)

    pager = ObjectPager(PageNode, page_size=10)
    first = await pager.get_page(page=1)
    assert len(first) == 4

    # Add a node and re-page — must see the new node, not a cached
    # 4-item snapshot.
    extra = PageNode(name="n_extra", value=99)
    await context.save(extra)

    refreshed = await pager.get_page(page=1)
    assert len(refreshed) == 5
    assert any(n.name == "n_extra" for n in refreshed)
