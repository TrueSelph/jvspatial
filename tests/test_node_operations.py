import pytest

from jvspatial.core import Edge, GraphContext, Node


# Define a custom edge class for testing
class CustomEdge(Edge):
    # Add __test__ attribute to prevent pytest from collecting it as a test
    __test__ = False


@pytest.fixture(scope="module")
async def context():
    ctx = GraphContext()
    yield ctx
    # No close method exists, so removed await ctx.close()


@pytest.fixture(autouse=True)
async def cleanup(context):
    # Clean up before each test
    await context.database.delete_many("node", {})
    await context.database.delete_many("edge", {})


@pytest.mark.asyncio
async def test_basic_disconnect(context):
    node1 = await Node.create()
    node2 = await Node.create()
    await node1.connect(node2)

    assert await node1.is_connected_to(node2)
    success = await node1.disconnect(node2)
    assert success
    assert not await node1.is_connected_to(node2)


@pytest.mark.asyncio
async def test_disconnect_specific_edge_type(context):
    node1 = await Node.create()
    node2 = await Node.create()
    await node1.connect(node2, edge=CustomEdge)
    await node1.connect(node2, edge=Edge)  # Different edge type

    # Disconnect only CustomEdge connections
    success = await node1.disconnect(node2, edge_type=CustomEdge)
    assert success

    # Should still be connected via Edge type
    assert await node1.is_connected_to(node2)


@pytest.mark.asyncio
async def test_disconnect_non_connected_nodes(context):
    node1 = await Node.create()
    node2 = await Node.create()

    success = await node1.disconnect(node2)
    assert not success  # Should return False when no connection exists


@pytest.mark.asyncio
async def test_edge_removal_from_both_nodes(context):
    node1 = await Node.create()
    node2 = await Node.create()
    await node1.connect(node2)

    initial_edges_node1 = len(node1.edge_ids)
    initial_edges_node2 = len(node2.edge_ids)

    await node1.disconnect(node2)

    assert len(node1.edge_ids) == initial_edges_node1 - 1
    assert len(node2.edge_ids) == initial_edges_node2 - 1
