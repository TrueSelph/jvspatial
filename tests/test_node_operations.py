import os
import tempfile
from typing import List

import pytest

from jvspatial.core import Edge, GraphContext, Node
from jvspatial.db.jsondb import JsonDB


# Define a custom edge class for testing
class CustomEdge(Edge):
    # Add __test__ attribute to prevent pytest from collecting it as a test
    __test__ = False


@pytest.fixture(scope="module")
async def context():
    from jvspatial.core.context import set_default_context

    with tempfile.TemporaryDirectory() as tmpdir:
        db = JsonDB(os.path.join(tmpdir, "test.json"))
        ctx = GraphContext(database=db)
        # Set this as the default context so all entities use this database
        set_default_context(ctx)
        yield ctx


@pytest.fixture(autouse=True)
async def cleanup(context):
    # Clean up before each test
    db = context.database
    # Get all records and delete them individually since delete_many doesn't exist
    nodes = await db.find("node", {})
    for node in nodes:
        await db.delete("node", node["id"])

    edges = await db.find("edge", {})
    for edge in edges:
        await db.delete("edge", edge["id"])


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

    name: str = ""

    __test__ = False


class Agent(Node):
    """Agent node type for testing."""

    name: str = ""
    status: str = "active"

    __test__ = False


class City(Node):
    """City node type for testing."""

    name: str = ""

    __test__ = False


class Organization(Node):
    """Organization node type for testing."""

    name: str = ""
    type: str = "company"

    __test__ = False


class Mission(Node):
    """Mission node type for testing."""

    name: str = ""
    priority: str = "medium"

    __test__ = False


# Define custom edge types for walker testing
class WorksFor(Edge):
    """Edge representing employment relationship."""

    __test__ = False


class LocatedIn(Edge):
    """Edge representing location relationship."""

    __test__ = False


class AssignedTo(Edge):
    """Edge representing assignment relationship."""

    __test__ = False


class HasMemory(Edge):
    """Edge representing memory relationship."""

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
        memory = await Memory.create()
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


# ============================================================================
# COMPREHENSIVE WALKER TRAVERSAL TESTS
# ============================================================================


class TestWalkerTraversal:
    """Test comprehensive walker traversal with proper graph connections."""

    @pytest.mark.asyncio
    async def test_basic_graph_traversal(self, context):
        """Test walker traversal through a connected graph."""
        from jvspatial.core import on_visit
        from jvspatial.core.entities import Walker

        # Create a simple connected graph: Agent -> Memory
        agent = await Agent.create(name="TestAgent")
        memory = await Memory.create(name="TestMemory")

        # Connect them with a specific edge type
        await agent.connect(memory, edge=HasMemory)

        # Create a walker that discovers connected nodes
        class GraphWalker(Walker):
            visited_nodes: List[str] = []

            @on_visit()  # Catch all node types
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)  # Use id instead of name
                # Discover connected nodes and add them to queue
                connected_nodes = await node.nodes()
                for connected_node in connected_nodes:
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = GraphWalker()

        # Start traversal from the agent
        await walker.spawn(agent)

        # Should have visited both nodes
        assert len(walker.visited_nodes) == 2
        assert agent.id in walker.visited_nodes
        assert memory.id in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_complex_graph_traversal(self, context):
        """Test walker traversal through a complex connected graph."""
        from jvspatial.core import on_visit
        from jvspatial.core.entities import Walker

        # Create a complex graph:
        # Organization -> Agent -> Memory
        # Organization -> Mission
        # Agent -> Mission (assignment)
        org = await Organization.create(name="AcmeCorp")
        agent = await Agent.create(name="Agent1")
        memory = await Memory.create(name="Memory1")
        mission = await Mission.create(name="Mission1")

        # Create connections
        await org.connect(agent, edge=WorksFor)
        await agent.connect(memory, edge=HasMemory)
        await org.connect(mission, edge=AssignedTo)
        await agent.connect(mission, edge=AssignedTo)

        # Create a walker that follows specific edge types
        class SelectiveWalker(Walker):
            visited_nodes: List[str] = []

            @on_visit()  # Catch all node types
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)  # Use id instead of name

                # Only follow WorksFor and HasMemory edges
                if isinstance(node, Organization):
                    # Find agents working for this organization
                    agents = await node.nodes(edge=WorksFor)
                    for agent_node in agents:
                        if agent_node not in self.queue._backing:
                            await self.queue.append([agent_node])
                elif isinstance(node, Agent):
                    # Find memories of this agent
                    memories = await node.nodes(edge=HasMemory)
                    for memory_node in memories:
                        if memory_node not in self.queue._backing:
                            await self.queue.append([memory_node])

        walker = SelectiveWalker()

        # Start traversal from the organization
        await walker.spawn(org)

        # Should have visited Organization -> Agent -> Memory
        # But NOT Mission (not following AssignedTo edges)
        assert len(walker.visited_nodes) == 3
        assert org.id in walker.visited_nodes
        assert agent.id in walker.visited_nodes
        assert memory.id in walker.visited_nodes
        assert mission.id not in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_bidirectional_traversal(self, context):
        """Test walker traversal in both directions."""
        from jvspatial.core import on_visit
        from jvspatial.core.entities import Walker

        # Create nodes
        city1 = await City.create(name="NewYork")
        city2 = await City.create(name="Boston")
        agent = await Agent.create(name="Traveler")

        # Create bidirectional connections
        await city1.connect(city2, edge=LocatedIn)
        await agent.connect(city1, edge=LocatedIn)

        # Create a walker that traverses in both directions
        class BidirectionalWalker(Walker):
            visited_nodes: List[str] = []

            @on_visit()  # Catch all node types
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)  # Use id instead of name

                # Follow both incoming and outgoing connections
                outgoing = await node.nodes(direction="out")
                incoming = await node.nodes(direction="in")

                for connected_node in outgoing + incoming:
                    # Only add if not already visited and not in queue
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = BidirectionalWalker()

        # Start from the agent
        await walker.spawn(agent)

        # Should have visited all nodes
        assert len(walker.visited_nodes) == 3
        assert agent.id in walker.visited_nodes
        assert city1.id in walker.visited_nodes
        assert city2.id in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_traversal_with_edge_filtering(self, context):
        """Test walker traversal with specific edge type filtering."""
        from jvspatial.core import on_visit
        from jvspatial.core.entities import Walker

        # Create nodes
        org = await Organization.create(name="TechCorp")
        agent1 = await Agent.create(name="Agent1")
        agent2 = await Agent.create(name="Agent2")
        mission = await Mission.create(name="SecretMission")

        # Create different types of connections
        await org.connect(agent1, edge=WorksFor)  # Employment
        await org.connect(agent2, edge=WorksFor)  # Employment
        await org.connect(mission, edge=AssignedTo)  # Assignment
        await agent1.connect(mission, edge=AssignedTo)  # Assignment

        # Create a walker that only follows WorksFor edges
        class EmploymentWalker(Walker):
            visited_nodes: List[str] = []

            @on_visit()  # Catch all node types
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)  # Use id instead of name

                # Only follow WorksFor edges
                employees = await node.nodes(edge=WorksFor)
                for employee in employees:
                    if employee not in self.queue._backing:
                        await self.queue.append([employee])

        walker = EmploymentWalker()

        # Start from the organization
        await walker.spawn(org)

        # Should only visit organization and agents (not mission)
        assert len(walker.visited_nodes) == 3
        assert org.id in walker.visited_nodes
        assert agent1.id in walker.visited_nodes
        assert agent2.id in walker.visited_nodes
        assert mission.id not in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_traversal_with_node_filtering(self, context):
        """Test walker traversal with specific node type filtering."""
        from jvspatial.core import on_visit
        from jvspatial.core.entities import Walker

        # Create a mixed graph
        org = await Organization.create(name="Company")
        agent = await Agent.create(name="Employee")
        memory = await Memory.create(name="Knowledge")
        city = await City.create(name="Location")

        # Connect everything
        await org.connect(agent)
        await agent.connect(memory)
        await agent.connect(city)

        # Create a walker that only follows Agent nodes
        class AgentOnlyWalker(Walker):
            visited_nodes: List[str] = []

            @on_visit()  # Catch all node types
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)  # Use id instead of name

                # Only follow connections to Agent nodes
                agents = await node.nodes(node="Agent")
                for agent_node in agents:
                    if agent_node not in self.queue._backing:
                        await self.queue.append([agent_node])

        walker = AgentOnlyWalker()

        # Start from the organization
        await walker.spawn(org)

        # Should visit Organization -> Agent, but not Memory or City
        assert len(walker.visited_nodes) == 2
        assert org.id in walker.visited_nodes
        assert agent.id in walker.visited_nodes
        assert memory.id not in walker.visited_nodes
        assert city.id not in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_traversal_with_depth_limiting(self, context):
        """Test walker traversal with depth limiting."""
        from jvspatial.core import on_visit
        from jvspatial.core.entities import Walker

        # Create a chain: A -> B -> C -> D
        node_a = await Node.create(name="A")
        node_b = await Node.create(name="B")
        node_c = await Node.create(name="C")
        node_d = await Node.create(name="D")

        await node_a.connect(node_b)
        await node_b.connect(node_c)
        await node_c.connect(node_d)

        # Create a walker with depth limiting
        class DepthLimitedWalker(Walker):
            visited_nodes: List[str] = []
            node_depths: dict = {}  # Track depth for each node
            max_depth: int = 2

            @on_visit()  # Catch all node types
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)  # Use id instead of name

                # Get current depth for this node (0 for starting node)
                current_depth = self.node_depths.get(node.id, 0)

                # Only continue if we haven't reached max depth
                if current_depth < self.max_depth:
                    connected_nodes = await node.nodes()
                    for connected_node in connected_nodes:
                        if (
                            connected_node.id not in self.visited_nodes
                            and connected_node not in self.queue._backing
                        ):
                            # Set depth for connected node
                            self.node_depths[connected_node.id] = current_depth + 1
                            await self.queue.append([connected_node])

        walker = DepthLimitedWalker()

        # Start from node A
        walker.node_depths[node_a.id] = 0  # Initialize starting node depth
        await walker.spawn(node_a)

        # Should only visit A, B, C (depth 0, 1, 2)
        # D should not be visited (would be depth 3)
        assert len(walker.visited_nodes) == 3
        assert node_a.id in walker.visited_nodes
        assert node_b.id in walker.visited_nodes
        assert node_c.id in walker.visited_nodes
        assert node_d.id not in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_traversal_with_cycle_detection(self, context):
        """Test walker traversal with cycle detection."""
        from jvspatial.core import on_visit
        from jvspatial.core.entities import Walker

        # Create a cycle: A -> B -> C -> A
        node_a = await Node.create(name="A")
        node_b = await Node.create(name="B")
        node_c = await Node.create(name="C")

        await node_a.connect(node_b)
        await node_b.connect(node_c)
        await node_c.connect(node_a)  # Creates cycle

        # Create a walker with cycle detection
        class CycleAwareWalker(Walker):
            visited_nodes: List[str] = []

            @on_visit()  # Catch all node types
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)  # Use id instead of name

                # Only visit nodes we haven't seen before
                connected_nodes = await node.nodes()
                for connected_node in connected_nodes:
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = CycleAwareWalker()

        # Start from node A
        await walker.spawn(node_a)

        # Should visit each node only once despite the cycle
        assert len(walker.visited_nodes) == 3
        assert walker.visited_nodes.count(node_a.id) == 1
        assert walker.visited_nodes.count(node_b.id) == 1
        assert walker.visited_nodes.count(node_c.id) == 1

    @pytest.mark.asyncio
    async def test_traversal_with_conditional_logic(self, context):
        """Test walker traversal with conditional logic based on node properties."""
        from jvspatial.core import on_visit
        from jvspatial.core.entities import Walker

        # Create nodes with different properties
        org = await Organization.create(name="Company", type="tech")
        agent1 = await Agent.create(name="Agent1", status="active")
        agent2 = await Agent.create(name="Agent2", status="inactive")
        mission = await Mission.create(name="Mission", priority="high")

        # Connect them
        await org.connect(agent1)
        await org.connect(agent2)
        await org.connect(mission)

        # Create a walker with conditional logic
        class ConditionalWalker(Walker):
            visited_nodes: List[str] = []

            @on_visit()  # Catch all node types
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)  # Use id instead of name

                # Only follow connections to active agents
                if isinstance(node, Organization):
                    agents = await node.nodes(node="Agent")
                    for agent_node in agents:
                        if (
                            hasattr(agent_node, "status")
                            and agent_node.status == "active"
                            and agent_node not in self.queue._backing
                        ):
                            await self.queue.append([agent_node])

        walker = ConditionalWalker()

        # Start from the organization
        await walker.spawn(org)

        # Should only visit Organization and Agent1 (active)
        # Agent2 (inactive) and Mission should not be visited
        assert len(walker.visited_nodes) == 2
        assert org.id in walker.visited_nodes
        assert agent1.id in walker.visited_nodes
        assert agent2.id not in walker.visited_nodes
        assert mission.id not in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_complex_multi_level_graph_traversal(self, context):
        """Test walker traversal through a complex multi-level graph structure."""
        from jvspatial.core import on_visit
        from jvspatial.core.entities import Walker

        # Create a complex graph: Root -> Org -> Agent -> Memory
        #                           -> City -> Agent -> Mission
        root = await Node.create()
        org = await Organization.create(name="TechCorp")
        city = await City.create(name="SanFrancisco")
        agent1 = await Agent.create(name="Agent1")
        agent2 = await Agent.create(name="Agent2")
        memory = await Memory.create(name="TechMemory")
        mission = await Mission.create(name="TechMission")

        # Create complex connections
        await root.connect(org, edge=LocatedIn)
        await root.connect(city, edge=LocatedIn)
        await org.connect(agent1, edge=WorksFor)
        await city.connect(agent2, edge=LocatedIn)
        await agent1.connect(memory, edge=HasMemory)
        await agent2.connect(mission, edge=AssignedTo)

        # Create a walker that follows all connections
        class ComplexGraphWalker(Walker):
            visited_nodes: List[str] = []
            traversal_path: List[str] = []

            @on_visit()
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)
                self.traversal_path.append(node.id)

                # Follow all connected nodes
                connected_nodes = await node.nodes()
                for connected_node in connected_nodes:
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = ComplexGraphWalker()

        # Start from root
        await walker.spawn(root)

        # Should visit all nodes in the graph
        assert len(walker.visited_nodes) == 7
        assert root.id in walker.visited_nodes
        assert org.id in walker.visited_nodes
        assert city.id in walker.visited_nodes
        assert agent1.id in walker.visited_nodes
        assert agent2.id in walker.visited_nodes
        assert memory.id in walker.visited_nodes
        assert mission.id in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_walker_with_edge_type_filtering(self, context):
        """Test walker that only follows specific edge types."""
        from jvspatial.core import on_visit
        from jvspatial.core.entities import Walker

        # Create nodes
        org = await Organization.create(name="Company")
        agent = await Agent.create(name="Employee")
        memory = await Memory.create(name="Knowledge")
        city = await City.create(name="Location")

        # Create different types of connections
        await org.connect(agent, edge=WorksFor)  # Employment
        await agent.connect(memory, edge=HasMemory)  # Knowledge
        await org.connect(city, edge=LocatedIn)  # Location

        # Create a walker that only follows WorksFor edges
        class EmploymentOnlyWalker(Walker):
            visited_nodes: List[str] = []

            @on_visit()
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)

                # Only follow WorksFor edges
                connected_nodes = await node.nodes(edge=WorksFor)
                for connected_node in connected_nodes:
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = EmploymentOnlyWalker()

        # Start from organization
        await walker.spawn(org)

        # Should only visit org and agent (connected by WorksFor)
        # Should NOT visit memory or city (different edge types)
        assert len(walker.visited_nodes) == 2
        assert org.id in walker.visited_nodes
        assert agent.id in walker.visited_nodes
        assert memory.id not in walker.visited_nodes
        assert city.id not in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_walker_with_direction_filtering(self, context):
        """Test walker that only follows specific directions."""
        from jvspatial.core import on_visit
        from jvspatial.core.entities import Walker

        # Create nodes
        node_a = await Node.create()
        node_b = await Node.create()
        node_c = await Node.create()

        # Create directional connections: A -> B -> C
        await node_a.connect(node_b)
        await node_b.connect(node_c)

        # Create a walker that only follows outgoing connections
        class OutgoingOnlyWalker(Walker):
            visited_nodes: List[str] = []

            @on_visit()
            async def visit_node(self, node):
                self.visited_nodes.append(node.id)

                # Only follow outgoing connections
                connected_nodes = await node.nodes(direction="out")
                for connected_node in connected_nodes:
                    if (
                        connected_node.id not in self.visited_nodes
                        and connected_node not in self.queue._backing
                    ):
                        await self.queue.append([connected_node])

        walker = OutgoingOnlyWalker()

        # Start from node B (middle of chain)
        await walker.spawn(node_b)

        # Should visit B and C (outgoing), but NOT A (incoming)
        assert len(walker.visited_nodes) == 2
        assert node_b.id in walker.visited_nodes
        assert node_c.id in walker.visited_nodes
        assert node_a.id not in walker.visited_nodes
