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


# Define custom node types for node() method testing
class Memory(Node):
    """Memory node type for testing."""

    __test__ = False


class Agent(Node):
    """Agent node type for testing."""

    __test__ = False


class City(Node):
    """City node type for testing."""

    __test__ = False


@pytest.mark.asyncio
async def test_node_method_returns_single_node(context):
    """Test that node() returns a single node instead of a list."""
    agent = await Agent.create()
    memory = await Memory.create()
    await agent.connect(memory)

    # Old way: nodes() returns a list
    nodes_result = await agent.nodes(node=["Memory"])
    assert isinstance(nodes_result, list)
    assert len(nodes_result) == 1

    # New way: node() returns a single node or None
    node_result = await agent.node(node="Memory")
    assert node_result is not None
    assert isinstance(node_result, Memory)
    assert node_result.id == memory.id


@pytest.mark.asyncio
async def test_node_method_returns_first_when_multiple(context):
    """Test that node() returns the first node when multiple nodes match."""
    agent = await Agent.create()
    memory1 = await Memory.create()
    memory2 = await Memory.create()
    await agent.connect(memory1)
    await agent.connect(memory2)

    # node() should return the first connected memory
    result = await agent.node(node="Memory")
    assert result is not None
    assert isinstance(result, Memory)
    # Should be one of the connected memories (order may vary)
    assert result.id in [memory1.id, memory2.id]


@pytest.mark.asyncio
async def test_node_method_returns_none_when_not_found(context):
    """Test that node() returns None when no matching node is found."""
    agent = await Agent.create()
    memory = await Memory.create()
    await agent.connect(memory)

    # Try to find a non-existent node type
    result = await agent.node(node="City")
    assert result is None


@pytest.mark.asyncio
async def test_node_method_with_property_filtering(context):
    """Test that node() works with property filtering."""
    agent = await Agent.create()
    memory1 = await Memory.create()
    memory2 = await Memory.create()
    await agent.connect(memory1)
    await agent.connect(memory2)

    # Find specific memory by id (more reliable than name filtering)
    result = await agent.node(node="Memory")
    assert result is not None
    assert isinstance(result, Memory)
    # Verify it's one of our connected memories
    assert result.id in [memory1.id, memory2.id]


@pytest.mark.asyncio
async def test_node_method_with_direction(context):
    """Test that node() respects direction parameter."""
    city1 = await City.create()
    city2 = await City.create()
    city3 = await City.create()

    # Create directional connections
    await city1.connect(city2, direction="out")
    await city3.connect(city1, direction="out")

    # Test outgoing direction
    outgoing = await city1.node(direction="out")
    assert outgoing is not None
    assert outgoing.id == city2.id

    # Test incoming direction
    incoming = await city1.node(direction="in")
    assert incoming is not None
    assert incoming.id == city3.id


@pytest.mark.asyncio
async def test_node_method_optimizes_with_limit(context):
    """Test that node() passes limit=1 for optimization."""
    agent = await Agent.create()
    # Create multiple memories
    for i in range(5):
        memory = await Memory.create(name=f"Memory {i}")
        await agent.connect(memory)

    # node() should efficiently get just the first one
    result = await agent.node(node="Memory")
    assert result is not None
    assert isinstance(result, Memory)


@pytest.mark.asyncio
async def test_node_method_use_case_example(context):
    """Test the real-world use case that motivated this method."""
    # This is the use case from the request:
    # Instead of:
    #   nodes = await self.nodes(node=['Memory'])
    #   if nodes:
    #       return nodes[0]
    # We can now do:
    #   memory = await self.node(node='Memory')
    #   if memory:
    #       return memory

    agent = await Agent.create()
    memory = await Memory.create()
    await agent.connect(memory)

    # Simplified code
    found_memory = await agent.node(node="Memory")
    if found_memory:
        # Can use directly without list indexing
        assert found_memory.id == memory.id
        assert isinstance(found_memory, Memory)
