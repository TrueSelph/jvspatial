"""Regression tests for the single-hop ``find_connected_nodes`` fast path.

Both bugs below shipped in 0.0.10 because the stock ``JsonDB`` used by the
rest of the suite exposes no ``find_connected_nodes`` method, so ``_node_query``
silently fell back to the slow edge-scan path and the fast path went untested.
These tests install a minimal ``find_connected_nodes`` shim to exercise it.

Bug 1 — limit-before-filter: ``limit`` was pushed into the DB scan *before* the
Python node-type filter, so ``nodes(node=T, limit=1)`` could return nothing when
the first raw neighbor was a different type, even though matching neighbors
existed.

Bug 2 — subtype resolution under an entity-name collision: the fast path
deserialized every row with the base ``Node`` class, so when two ``Node``
subclasses shared an entity name (e.g. an app ``User`` and an embedded-agent
``User`` persisted in one database) ``find_subclass_by_name`` returned the first
global match and ``_matches_node_filter``'s ``isinstance`` check dropped the
valid neighbor.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities.node import Node
from jvspatial.db.jsondb import JsonDB


class _FastJsonDB(JsonDB):
    """JsonDB plus a ``find_connected_nodes`` so the fast path is exercised.

    Mirrors the Postgres backend contract: strict source/target endpoints per
    ``direction`` and DB-side ``limit`` applied to the raw (unfiltered) rows.
    """

    async def find_connected_nodes(
        self,
        node_collection: str,
        edge_collection: str,
        node_id: str,
        *,
        direction: str = "out",
        edge_entity: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        edges = await self.find(edge_collection, {})
        rows: List[Dict[str, Any]] = []
        for e in edges:
            src, tgt = e.get("source"), e.get("target")
            if direction == "out" and src == node_id:
                other = tgt
            elif direction == "in" and tgt == node_id:
                other = src
            else:
                continue
            if edge_entity is not None and e.get("entity") != edge_entity:
                continue
            n = await self.get(node_collection, other)
            if n is not None:
                rows.append(n)
        # Deterministic order (Postgres has no implicit ORDER BY, so the bug
        # surfaces whenever a non-matching neighbor happens to sort first).
        rows.sort(key=lambda r: r["id"])
        if limit is not None:
            rows = rows[:limit]
        return rows


class Widget(Node):
    """A distinct child type used to prove type-filtered fetches."""

    label: str = ""


class Gadget(Node):
    """A different child type sharing the parent but not the filter."""

    label: str = ""


# Two subclasses that intentionally share one entity name — the collision that
# broke subtype resolution on the fast path.
class AlphaAccount(Node):
    __entity_name__ = "CollidingAccount"
    label: str = ""


class BetaAccount(Node):
    __entity_name__ = "CollidingAccount"
    label: str = ""


@pytest.fixture
async def ctx(tmp_path):
    context = GraphContext(database=_FastJsonDB(base_path=str(tmp_path)))
    set_default_context(context)
    yield context


@pytest.mark.asyncio
async def test_type_filter_with_limit_is_not_truncated_before_filtering(ctx):
    """``nodes(node=Widget, limit=1)`` returns a Widget even when a non-Widget
    neighbor sorts first — limit must apply after the type filter."""
    parent = Node()
    # ids chosen so the non-matching Gadget sorts first — a DB-side limit of 1
    # would grab only the Gadget and then filter it out (the bug).
    gadget = Gadget(id="n.Gadget.0000", label="g")
    w1 = Widget(id="n.Widget.1111", label="w1")
    w2 = Widget(id="n.Widget.2222", label="w2")
    for n in (parent, gadget, w1, w2):
        await ctx.save(n)
    await parent.connect(gadget)
    await parent.connect(w1)
    await parent.connect(w2)

    one = await parent.nodes(node=Widget, direction="out", limit=1)
    assert len(one) == 1
    assert isinstance(one[0], Widget)

    got = await parent.node(node=Widget, direction="out")
    assert got is not None and isinstance(got, Widget)


@pytest.mark.asyncio
async def test_subtype_resolved_under_entity_name_collision(ctx):
    """When two Node subclasses share an entity name, the fast path hydrates the
    concrete class the caller filtered on (not the first global name match)."""
    parent = Node()
    beta = BetaAccount(label="beta")
    for n in (parent, beta):
        await ctx.save(n)
    await parent.connect(beta)

    # AlphaAccount is defined first, so an unhinted global name lookup for
    # "CollidingAccount" resolves to Alpha — the old bug dropped the Beta row.
    got = await parent.node(node=BetaAccount, direction="out")
    assert got is not None, "subtype filter dropped a valid neighbor (bug 2)"
    assert isinstance(got, BetaAccount)
    assert got.id == beta.id

    many = await parent.nodes(node=BetaAccount, direction="out")
    assert [n.id for n in many] == [beta.id]
