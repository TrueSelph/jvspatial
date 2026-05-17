"""Walker and save-cycle coverage for ``__entity_name__`` override (audit §1).

Walker now ships its own ``__entity_name__`` classmethod parallel to
``Object._entity_name`` so walker IDs and the persisted ``entity`` field
honor the per-subclass discriminator. The previous behavior used
``cls.__name__`` unconditionally, which broke the override for walkers
entirely.

``GraphContext.save_object`` previously regenerated entity IDs when
``id_parts[1] != cls.__name__`` — that check used ``__name__`` instead of
``_entity_name()``, so every save of an override-using class rewrote the
ID with the wrong discriminator. The fix uses ``_entity_name()`` so saves
are stable.

``GraphContext.find_edges_between`` previously queried
``entity == edge_class.__name__``; an edge subclass with
``__entity_name__`` would never match its own rows.
"""

import tempfile
import uuid

import pytest

from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Edge, Node, Walker
from jvspatial.db import create_database


class CustomNamedWalker(Walker):
    __entity_name__ = "FleetTraversalWalker"


class CustomNamedEdge(Edge):
    __entity_name__ = "FleetLink"
    weight: float = 1.0


class FleetNode(Node):
    label: str = ""


@pytest.fixture
def json_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        unique_path = f"{tmpdir}/test_{uuid.uuid4().hex}"
        database = create_database("json", base_path=unique_path)
        yield GraphContext(database=database)


def test_walker_id_honors_entity_name_override():
    walker = CustomNamedWalker()
    # ID prefix and persisted entity must reflect the override, not the
    # Python class name.
    assert walker.id.startswith("w.FleetTraversalWalker.")
    assert walker.entity == "FleetTraversalWalker"


def test_walker_entity_name_classmethod():
    assert CustomNamedWalker._entity_name() == "FleetTraversalWalker"

    # Per-subclass — not inherited from a parent that happens to override.
    class GrandchildWalker(CustomNamedWalker):
        pass

    assert GrandchildWalker._entity_name() == "GrandchildWalker"


@pytest.mark.asyncio
async def test_save_does_not_rewrite_override_ids(json_context):
    """``GraphContext.save_object`` must not regenerate IDs that use the
    override.

    Before the §1 fix, the ID-validation check at context.py:753 compared
    against ``__name__``, so any class with ``__entity_name__`` had its
    ID rewritten on every save — silent data corruption.
    """

    class WidgetNode(Node):
        __entity_name__ = "MarketplaceWidget"
        name: str = ""

    n = WidgetNode(name="alpha")
    original_id = n.id
    assert original_id.startswith("n.MarketplaceWidget.")

    await json_context.save(n)
    # ID is unchanged after save.
    assert n.id == original_id

    # And on a second save (covers the regeneration branch).
    await json_context.save(n)
    assert n.id == original_id


@pytest.mark.asyncio
async def test_find_edges_between_honors_override(json_context):
    """``find_edges_between`` builds an ``entity == edge_class._entity_name()``
    query rather than ``__name__`` so override edges are findable."""
    a = FleetNode(label="A")
    b = FleetNode(label="B")
    await json_context.save(a)
    await json_context.save(b)

    edge = CustomNamedEdge(source=a.id, target=b.id, weight=2.0)
    await json_context.save(edge)
    assert edge.entity == "FleetLink"
    assert edge.id.startswith("e.FleetLink.")

    found = await json_context.find_edges_between(
        source_id=a.id, target_id=b.id, edge_class=CustomNamedEdge
    )
    assert len(found) == 1
    assert found[0].id == edge.id
