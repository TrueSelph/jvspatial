"""Comprehensive test suite for entity CRUD operations and node cascade deletion.

Tests:
- Entity CRUD operations (Create, Read, Update, Delete) for all entity types
- Node cascade deletion with edges
- Node cascade deletion with dependent nodes (solely connected nodes)
- Node deletion without cascade
- Object deletion (simple, no cascade)
- Edge deletion (simple, no cascade)
- Context.delete() delegation to Node.delete() for nodes
"""

import tempfile
from typing import Optional

import pytest
from pydantic import Field

from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Edge, Node, Object
from jvspatial.db.factory import create_database


# Test entity classes
class TestNode(Node):
    """Test node for CRUD and cascade testing."""

    __test__ = False  # Prevent pytest from collecting as test class

    name: str = ""
    value: int = 0
    type_code: str = Field(default="n")


class TestEdge(Edge):
    """Test edge for CRUD and cascade testing."""

    __test__ = False  # Prevent pytest from collecting as test class

    weight: int = 1
    type_code: str = Field(default="e")


class TestObject(Object):
    """Test object for CRUD testing."""

    __test__ = False  # Prevent pytest from collecting as test class

    name: str = ""
    value: int = 0
    active: bool = True
    type_code: str = Field(default="o")


class TestGraphContextCRUD:
    """Test comprehensive CRUD operations for all entity types."""

    @pytest.fixture
    def temp_context(self):
        """Create temporary context for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import uuid

            unique_path = f"{tmpdir}/test_{uuid.uuid4().hex}"
            config = {"db_type": "json", "db_config": {"base_path": unique_path}}
            database = create_database(config["db_type"], **config["db_config"])
            context = GraphContext(database=database)
            yield context

    @pytest.mark.asyncio
    async def test_node_create(self, temp_context):
        """Test node creation."""
        node = await TestNode.create(name="test_node", value=42)
        assert node.id is not None
        assert node.name == "test_node"
        assert node.value == 42
        assert len(node.edge_ids) == 0

    @pytest.mark.asyncio
    async def test_node_read(self, temp_context):
        """Test node retrieval."""
        # Create node
        created = await TestNode.create(name="test_node", value=42)
        node_id = created.id

        # Retrieve node
        retrieved = await TestNode.get(node_id)
        assert retrieved is not None
        assert retrieved.id == node_id
        assert retrieved.name == "test_node"
        assert retrieved.value == 42

    @pytest.mark.asyncio
    async def test_node_update(self, temp_context):
        """Test node update."""
        # Create node
        node = await TestNode.create(name="original", value=10)
        node_id = node.id

        # Update node
        node.name = "updated"
        node.value = 20
        await node.save()

        # Verify update
        retrieved = await TestNode.get(node_id)
        assert retrieved.name == "updated"
        assert retrieved.value == 20

    @pytest.mark.asyncio
    async def test_node_delete_simple(self, temp_context):
        """Test simple node deletion (no cascade)."""
        # Create node
        node = await TestNode.create(name="to_delete", value=42)
        node_id = node.id

        # Delete node
        await node.delete(cascade=False)

        # Verify deletion
        retrieved = await TestNode.get(node_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_object_create(self, temp_context):
        """Test object creation."""
        obj = await TestObject.create(name="test_object", value=42)
        assert obj.id is not None
        assert obj.name == "test_object"
        assert obj.value == 42

    @pytest.mark.asyncio
    async def test_object_read(self, temp_context):
        """Test object retrieval."""
        # Create object
        created = await TestObject.create(name="test_object", value=42)
        obj_id = created.id

        # Retrieve object
        retrieved = await TestObject.get(obj_id)
        assert retrieved is not None
        assert retrieved.id == obj_id
        assert retrieved.name == "test_object"
        assert retrieved.value == 42

    @pytest.mark.asyncio
    async def test_object_update(self, temp_context):
        """Test object update."""
        # Create object
        obj = await TestObject.create(name="original", value=10)
        obj_id = obj.id

        # Update object
        obj.name = "updated"
        obj.value = 20
        await obj.save()

        # Verify update
        retrieved = await TestObject.get(obj_id)
        assert retrieved.name == "updated"
        assert retrieved.value == 20

    @pytest.mark.asyncio
    async def test_object_delete(self, temp_context):
        """Test object deletion (simple, no cascade)."""
        # Create object
        obj = await TestObject.create(name="to_delete", value=42)
        obj_id = obj.id

        # Delete object
        await obj.delete()

        # Verify deletion
        retrieved = await TestObject.get(obj_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_object_count_all(self, temp_context):
        """Test counting all objects of a type."""
        from jvspatial.core.context import set_default_context

        set_default_context(temp_context)
        # Create multiple objects
        await TestObject.create(name="obj1", value=1, active=True)
        await TestObject.create(name="obj2", value=2, active=True)
        await TestObject.create(name="obj3", value=3, active=False)

        # Count all objects
        count = await TestObject.count()
        assert count == 3

    @pytest.mark.asyncio
    async def test_object_count_filtered(self, temp_context):
        """Test counting filtered objects."""
        from jvspatial.core.context import set_default_context

        set_default_context(temp_context)
        # Create multiple objects
        await TestObject.create(name="obj1", value=1, active=True)
        await TestObject.create(name="obj2", value=2, active=True)
        await TestObject.create(name="obj3", value=3, active=False)

        # Count filtered objects
        active_count = await TestObject.count({"context.active": True})
        assert active_count == 2

        inactive_count = await TestObject.count(active=False)
        assert inactive_count == 1

    @pytest.mark.asyncio
    async def test_node_count_all(self, temp_context):
        """Test counting all nodes of a type."""
        from jvspatial.core.context import set_default_context

        set_default_context(temp_context)
        # Create multiple nodes
        await TestNode.create(name="node1", value=1)
        await TestNode.create(name="node2", value=2)
        await TestNode.create(name="node3", value=3)

        # Count all nodes
        count = await TestNode.count()
        assert count == 3

    @pytest.mark.asyncio
    async def test_node_count_filtered(self, temp_context):
        """Test counting filtered nodes."""
        from jvspatial.core.context import set_default_context

        set_default_context(temp_context)
        # Create multiple nodes
        await TestNode.create(name="node1", value=1)
        await TestNode.create(name="node2", value=2)
        await TestNode.create(name="node3", value=3)

        # Count filtered nodes
        count = await TestNode.count({"context.value": 2})
        assert count == 1

        count_kwargs = await TestNode.count(value=3)
        assert count_kwargs == 1

    @pytest.mark.asyncio
    async def test_edge_count_all(self, temp_context):
        """Test counting all edges of a type."""
        from jvspatial.core.context import set_default_context

        set_default_context(temp_context)
        # Create nodes
        node1 = await TestNode.create(name="node1")
        node2 = await TestNode.create(name="node2")
        node3 = await TestNode.create(name="node3")

        # Create multiple edges
        await TestEdge.create(source=node1.id, target=node2.id, weight=1)
        await TestEdge.create(source=node2.id, target=node3.id, weight=2)
        await TestEdge.create(source=node1.id, target=node3.id, weight=3)

        # Count all edges
        count = await TestEdge.count()
        assert count == 3

    @pytest.mark.asyncio
    async def test_edge_count_filtered(self, temp_context):
        """Test counting filtered edges."""
        from jvspatial.core.context import set_default_context

        set_default_context(temp_context)
        # Create nodes
        node1 = await TestNode.create(name="node1")
        node2 = await TestNode.create(name="node2")
        node3 = await TestNode.create(name="node3")

        # Create multiple edges
        await TestEdge.create(source=node1.id, target=node2.id, weight=1)
        await TestEdge.create(source=node2.id, target=node3.id, weight=2)
        await TestEdge.create(source=node1.id, target=node3.id, weight=1)

        # Count filtered edges
        count = await TestEdge.count({"weight": 1})
        assert count == 2

        count_kwargs = await TestEdge.count(weight=2)
        assert count_kwargs == 1

    @pytest.mark.asyncio
    async def test_count_with_query_dict(self, temp_context):
        """Test that count() works with query dictionaries for all entity types."""
        from jvspatial.core.context import set_default_context

        set_default_context(temp_context)
        # Create test data
        await TestObject.create(name="obj1", value=1, active=True)
        await TestObject.create(name="obj2", value=2, active=False)

        node1 = await TestNode.create(name="node1", value=10)
        node2 = await TestNode.create(name="node2", value=20)

        await TestEdge.create(source=node1.id, target=node2.id, weight=5)

        # Test Object.count() with query dict
        obj_count = await TestObject.count({"context.active": True})
        assert obj_count == 1

        # Test Node.count() with query dict
        node_count = await TestNode.count({"context.value": 10})
        assert node_count == 1

        # Test Edge.count() with query dict
        edge_count = await TestEdge.count({"weight": 5})
        assert edge_count == 1

    @pytest.mark.asyncio
    async def test_edge_create(self, temp_context):
        """Test edge creation."""
        # Create nodes
        node1 = await TestNode.create(name="node1")
        node2 = await TestNode.create(name="node2")

        # Create edge
        edge = await TestEdge.create(source=node1.id, target=node2.id, weight=5)
        assert edge.id is not None
        assert edge.source == node1.id
        assert edge.target == node2.id
        assert edge.weight == 5

    @pytest.mark.asyncio
    async def test_edge_read(self, temp_context):
        """Test edge retrieval."""
        # Create nodes and edge
        node1 = await TestNode.create(name="node1")
        node2 = await TestNode.create(name="node2")
        created = await TestEdge.create(source=node1.id, target=node2.id, weight=5)
        edge_id = created.id

        # Retrieve edge
        retrieved = await TestEdge.get(edge_id)
        assert retrieved is not None
        assert retrieved.id == edge_id
        assert retrieved.source == node1.id
        assert retrieved.target == node2.id
        assert retrieved.weight == 5

    @pytest.mark.asyncio
    async def test_edge_update(self, temp_context):
        """Test edge update."""
        # Create nodes and edge
        node1 = await TestNode.create(name="node1")
        node2 = await TestNode.create(name="node2")
        edge = await TestEdge.create(source=node1.id, target=node2.id, weight=5)
        edge_id = edge.id

        # Update edge
        edge.weight = 10
        await edge.save()

        # Verify update
        retrieved = await TestEdge.get(edge_id)
        assert retrieved.weight == 10

    @pytest.mark.asyncio
    async def test_edge_delete(self, temp_context):
        """Test edge deletion (simple, no cascade)."""
        # Create nodes and edge
        node1 = await TestNode.create(name="node1")
        node2 = await TestNode.create(name="node2")
        edge = await TestEdge.create(source=node1.id, target=node2.id, weight=5)
        edge_id = edge.id

        # Delete edge
        await edge.delete()

        # Verify deletion
        retrieved = await TestEdge.get(edge_id)
        assert retrieved is None


class TestNodeCascadeDeletion:
    """Test node cascade deletion with edges and dependent nodes."""

    @pytest.fixture
    def temp_context(self):
        """Create temporary context for testing."""
        from jvspatial.core.context import set_default_context

        with tempfile.TemporaryDirectory() as tmpdir:
            import uuid

            unique_path = f"{tmpdir}/test_{uuid.uuid4().hex}"
            config = {"db_type": "json", "db_config": {"base_path": unique_path}}
            database = create_database(config["db_type"], **config["db_config"])
            context = GraphContext(database=database)
            # Set as default context so entity methods use it
            set_default_context(context)
            yield context

    @pytest.mark.asyncio
    async def test_node_delete_with_outgoing_edges(self, temp_context):
        """Test node deletion removes incoming edges only (outgoing edges remain until dependent nodes are deleted)."""
        # Create nodes
        parent = await TestNode.create(name="parent")
        child1 = await TestNode.create(name="child1")
        child2 = await TestNode.create(name="child2")

        # Create edges from parent to children (outgoing from parent, incoming to children)
        edge1 = await parent.connect(child1)
        edge2 = await parent.connect(child2)

        # Verify edges exist
        assert edge1.id in parent.edge_ids
        assert edge2.id in parent.edge_ids
        assert edge1.id in child1.edge_ids
        assert edge2.id in child2.edge_ids

        # Delete parent node without cascade (to preserve child nodes)
        await parent.delete(cascade=False)

        # Verify parent is deleted
        assert await temp_context.get(TestNode, parent.id) is None

        # With new implementation: only incoming edges to parent are deleted
        # Outgoing edges from parent remain until the target nodes are deleted
        # Since we're not cascading, child nodes are preserved, so edges remain
        # However, edges should be removed from parent's edge_ids (parent is deleted)
        # and from child nodes' edge_ids (since parent is deleted, edges are invalid)

        # Note: Current implementation only deletes incoming edges to the deleted node
        # Outgoing edges are not automatically deleted. They remain in the database
        # but should be cleaned up from child nodes' edge_ids
        child1_retrieved = await temp_context.get(TestNode, child1.id)
        child2_retrieved = await temp_context.get(TestNode, child2.id)
        assert child1_retrieved is not None
        assert child2_retrieved is not None
        # Edges are removed from child nodes' edge_ids when parent is deleted
        assert edge1.id not in child1_retrieved.edge_ids
        assert edge2.id not in child2_retrieved.edge_ids

    @pytest.mark.asyncio
    async def test_node_delete_with_incoming_edges(self, temp_context):
        """Test node deletion removes incoming edges."""
        # Create nodes
        parent = await TestNode.create(name="parent")
        child = await TestNode.create(name="child")

        # Create edge from child to parent (incoming for parent)
        edge = await child.connect(parent)

        # Verify edge exists
        assert edge.id in parent.edge_ids
        assert edge.id in child.edge_ids

        # Delete parent node without cascade (to preserve child node)
        await parent.delete(cascade=False)

        # Verify parent is deleted
        assert await temp_context.get(TestNode, parent.id) is None

        # Verify incoming edge to parent is deleted
        assert await temp_context.get(Edge, edge.id) is None

        # Verify edge_id is removed from child node (child preserved)
        child_retrieved = await temp_context.get(TestNode, child.id)
        assert child_retrieved is not None
        assert edge.id not in child_retrieved.edge_ids

    @pytest.mark.asyncio
    async def test_node_delete_with_bidirectional_edges(self, temp_context):
        """Test node deletion removes incoming edges (bidirectional edges are handled as incoming)."""
        # Create nodes
        node1 = await TestNode.create(name="node1")
        node2 = await TestNode.create(name="node2")

        # Create bidirectional edge
        edge = await node1.connect(node2, direction="both")

        # Verify edge exists in both nodes
        assert edge.id in node1.edge_ids
        assert edge.id in node2.edge_ids

        # Delete node1 without cascade (to preserve node2)
        await node1.delete(cascade=False)

        # Verify node1 is deleted
        assert await temp_context.get(TestNode, node1.id) is None

        # With new implementation: only incoming edges to node1 are deleted
        # For bidirectional edges, if node1 is the target, the edge is deleted
        # The edge should be removed from node2's edge_ids
        node2_retrieved = await temp_context.get(TestNode, node2.id)
        assert node2_retrieved is not None
        # Edge is removed from node2's edge_ids when node1 (target) is deleted
        assert edge.id not in node2_retrieved.edge_ids

    @pytest.mark.asyncio
    async def test_node_delete_cascade_solely_connected_nodes(self, temp_context):
        """Test node deletion cascades to solely connected dependent nodes."""
        from jvspatial.core.context import set_default_context

        # Set temp_context as default so entity methods use the same context
        set_default_context(temp_context)

        # Create a tree structure where children are solely connected to parent:
        # parent -> child1 (solely connected - only has edge to parent)
        # parent -> child2 (solely connected - only has edge to parent)
        # child1 -> grandchild (grandchild will be deleted when child1 is deleted)
        parent = await TestNode.create(name="parent")
        child1 = await TestNode.create(name="child1")
        child2 = await TestNode.create(name="child2")
        grandchild = await TestNode.create(name="grandchild")

        # Connect them - child1 and child2 are solely connected to parent
        edge1 = await parent.connect(child1)
        edge2 = await parent.connect(child2)
        # grandchild is solely connected to child1
        edge3 = await child1.connect(grandchild)

        # Delete parent with cascade
        await parent.delete(cascade=True)

        # Verify parent is deleted
        assert await temp_context.get(TestNode, parent.id) is None

        # Verify incoming edges to parent are deleted
        # Note: edge1 and edge2 are outgoing from parent, so they're cleaned up
        # when parent is deleted (removed from child nodes' edge_ids and deleted)

        # child1 is reachable FROM parent and has edge3 to grandchild
        # grandchild is also reachable FROM parent (via child1)
        # Since both child1 and grandchild are solely reachable from parent
        # (no external connections), they should both be deleted
        assert (
            await temp_context.get(TestNode, child1.id) is None
        ), "child1 should be deleted (solely reachable from parent)"
        assert (
            await temp_context.get(TestNode, child2.id) is None
        ), "child2 should be deleted (solely reachable from parent)"
        assert (
            await temp_context.get(TestNode, grandchild.id) is None
        ), "grandchild should be deleted (solely reachable from parent via child1)"

        # Verify edges are deleted
        assert await temp_context.get(Edge, edge1.id) is None
        assert await temp_context.get(Edge, edge2.id) is None
        assert await temp_context.get(Edge, edge3.id) is None

    @pytest.mark.asyncio
    async def test_node_delete_no_cascade_preserves_dependent_nodes(self, temp_context):
        """Test node deletion without cascade preserves dependent nodes."""
        # Create nodes
        parent = await TestNode.create(name="parent")
        child1 = await TestNode.create(name="child1")
        child2 = await TestNode.create(name="child2")

        # Connect them
        edge1 = await parent.connect(child1)
        edge2 = await parent.connect(child2)

        # Delete parent without cascade
        await parent.delete(cascade=False)

        # Verify parent is deleted
        assert await TestNode.get(parent.id) is None

        # With new implementation: only incoming edges to parent are deleted
        # Outgoing edges from parent (edge1, edge2) remain until target nodes are deleted
        # Since we're not cascading, child nodes are preserved
        # However, edges should be removed from child nodes' edge_ids

        # Verify child nodes are preserved (not cascaded)
        child1_retrieved = await TestNode.get(child1.id)
        child2_retrieved = await TestNode.get(child2.id)
        assert child1_retrieved is not None
        assert child2_retrieved is not None
        # Edges are removed from child nodes' edge_ids when parent is deleted
        assert edge1.id not in child1_retrieved.edge_ids
        assert edge2.id not in child2_retrieved.edge_ids

    @pytest.mark.asyncio
    async def test_node_delete_cascade_preserves_shared_nodes(self, temp_context):
        """Test node deletion with cascade preserves nodes with external connections."""
        from jvspatial.core.context import set_default_context

        set_default_context(temp_context)

        # Create nodes: parent -> child1 -> shared (external, has incoming edge from outside)
        #                      -> child2 -> shared
        # external_node -> shared (this makes shared truly external - not solely reachable from parent)
        parent = await TestNode.create(name="parent")
        child1 = await TestNode.create(name="child1")
        child2 = await TestNode.create(name="child2")
        shared = await TestNode.create(name="shared")
        external_node = await TestNode.create(name="external_node")

        # Connect parent to children
        edge1 = await parent.connect(child1)
        edge2 = await parent.connect(child2)

        # Connect children to shared
        edge3 = await child1.connect(shared)
        edge4 = await child2.connect(shared)

        # Connect external_node to shared (this makes shared external - not solely reachable from parent)
        edge_external_shared = await external_node.connect(shared)

        # Delete parent with cascade
        await parent.delete(cascade=True)

        # Verify parent is deleted
        assert await TestNode.get(parent.id) is None

        # Verify incoming edges to parent are deleted
        # Note: edge1 and edge2 are outgoing from parent, so they're cleaned up

        # child1 is reachable FROM parent, but has edge3 to shared
        # shared has an incoming edge from external_node (not reachable from parent)
        # This external connection prevents child1 from being deleted
        child1_retrieved = await TestNode.get(child1.id)
        assert (
            child1_retrieved is not None
        ), "child1 should be preserved (has connection to shared which has external connection)"
        assert (
            edge1.id not in child1_retrieved.edge_ids
        ), "edge1 should be removed from child1"
        assert edge3.id in child1_retrieved.edge_ids, "edge3 should remain in child1"

        # child2 is reachable FROM parent, but has edge4 to shared
        # shared has an incoming edge from external_node (not reachable from parent)
        # This external connection prevents child2 from being deleted
        child2_retrieved = await TestNode.get(child2.id)
        assert (
            child2_retrieved is not None
        ), "child2 should be preserved (has connection to shared which has external connection)"
        assert (
            edge2.id not in child2_retrieved.edge_ids
        ), "edge2 should be removed from child2"
        assert edge4.id in child2_retrieved.edge_ids, "edge4 should remain in child2"

        # Verify shared node is preserved (has external connection from external_node)
        shared_retrieved = await TestNode.get(shared.id)
        assert (
            shared_retrieved is not None
        ), "shared should be preserved (has external connection from external_node)"
        assert (
            edge_external_shared.id in shared_retrieved.edge_ids
        ), "edge from external_node should remain in shared"

        # Verify external_node is preserved (not reachable from parent)
        external_node_retrieved = await TestNode.get(external_node.id)
        assert (
            external_node_retrieved is not None
        ), "external_node should be preserved (not reachable from parent)"

    @pytest.mark.asyncio
    async def test_node_delete_complex_graph(self, temp_context):
        """Test node deletion in a complex graph structure."""
        # Create complex graph:
        #   A -> B -> C
        #   A -> D -> E
        #   B -> D
        node_a = await TestNode.create(name="A")
        node_b = await TestNode.create(name="B")
        node_c = await TestNode.create(name="C")
        node_d = await TestNode.create(name="D")
        node_e = await TestNode.create(name="E")

        # Create edges
        edge_ab = await node_a.connect(node_b)
        edge_bc = await node_b.connect(node_c)
        edge_ad = await node_a.connect(node_d)
        edge_de = await node_d.connect(node_e)
        edge_bd = await node_b.connect(node_d)

        # Delete node_a with cascade
        await node_a.delete(cascade=True)

        # Verify node_a is deleted
        assert await TestNode.get(node_a.id) is None

        # Verify incoming edges to node_a are deleted
        # Note: edge_ab and edge_ad are outgoing from node_a, incoming to node_b and node_d
        # With new implementation, only incoming edges to node_a are deleted

        # node_b is reachable FROM node_a, and has edge_bc (to node_c) and edge_bd (to node_d)
        # node_c is reachable FROM node_a (via node_b), and is only connected to node_b
        # So node_c should be deleted (solely reachable from node_a)
        # node_b has edge_bd to node_d, which is also reachable from node_a
        # But node_d has edge_de to node_e, which is also reachable from node_a
        # node_e is only connected to node_d, so it should be deleted

        # Verify node_c is deleted (solely reachable from node_a via node_b)
        assert (
            await TestNode.get(node_c.id) is None
        ), "node_c should be deleted (solely reachable from node_a)"

        # Verify node_e is deleted (solely reachable from node_a via node_d)
        assert (
            await TestNode.get(node_e.id) is None
        ), "node_e should be deleted (solely reachable from node_a)"

        # node_b is reachable FROM node_a, and has edge_bd to node_d
        # node_d is also reachable FROM node_a, so node_b's connection to node_d
        # is within the reachable set. However, node_b and node_d form a cycle
        # and both are reachable from node_a, so they should be deleted if solely reachable

        # Actually, node_b and node_d are both reachable from node_a and connected to each other
        # Since they're only reachable FROM node_a and have no external connections,
        # they should be deleted
        assert (
            await TestNode.get(node_b.id) is None
        ), "node_b should be deleted (solely reachable from node_a)"
        assert (
            await TestNode.get(node_d.id) is None
        ), "node_d should be deleted (solely reachable from node_a)"

        # Verify edges are deleted
        assert await Edge.get(edge_ab.id) is None
        assert await Edge.get(edge_ad.id) is None
        assert await Edge.get(edge_bc.id) is None
        assert await Edge.get(edge_bd.id) is None
        assert await Edge.get(edge_de.id) is None

    @pytest.mark.asyncio
    async def test_node_delete_cascade_hierarchical_structure(self, temp_context):
        """Test cascade delete with hierarchical structure: App -> Agents -> Agent -> Actions -> Action nodes.

        This test verifies that:
        - Only incoming edges to the deleted node are removed
        - Only nodes solely reachable from the deleted node are deleted
        - Ancestors (App, Agents) are preserved
        - Dependent nodes (Actions, Action nodes) are deleted
        """
        from jvspatial.core.context import set_default_context

        set_default_context(temp_context)

        # Create hierarchical structure: App -> Agents -> Agent -> Actions -> Action1, Action2
        app = await TestNode.create(name="App")
        agents = await TestNode.create(name="Agents")
        agent = await TestNode.create(name="Agent")
        actions = await TestNode.create(name="Actions")
        action1 = await TestNode.create(name="Action1")
        action2 = await TestNode.create(name="Action2")

        # Connect them (all outgoing edges from parent to child)
        edge_app_agents = await app.connect(agents)
        edge_agents_agent = await agents.connect(agent)
        edge_agent_actions = await agent.connect(actions)
        edge_actions_action1 = await actions.connect(action1)
        edge_actions_action2 = await actions.connect(action2)

        # Store IDs for verification
        app_id = app.id
        agents_id = agents.id
        agent_id = agent.id
        actions_id = actions.id
        action1_id = action1.id
        action2_id = action2.id

        # Delete agent with cascade
        await agent.delete(cascade=True)

        # Verify agent is deleted
        assert await TestNode.get(agent_id) is None

        # Verify incoming edge to agent is deleted
        assert await Edge.get(edge_agents_agent.id) is None

        # Verify ancestors are preserved (App and Agents)
        app_retrieved = await TestNode.get(app_id)
        agents_retrieved = await TestNode.get(agents_id)
        assert app_retrieved is not None, "App (ancestor) should be preserved"
        assert agents_retrieved is not None, "Agents (ancestor) should be preserved"

        # Verify edge from App to Agents is preserved
        assert edge_app_agents.id in app_retrieved.edge_ids
        assert edge_app_agents.id in agents_retrieved.edge_ids

        # Verify dependent nodes are deleted (Actions and Action nodes)
        assert (
            await TestNode.get(actions_id) is None
        ), "Actions should be deleted (solely reachable from Agent)"
        assert (
            await TestNode.get(action1_id) is None
        ), "Action1 should be deleted (solely reachable from Actions)"
        assert (
            await TestNode.get(action2_id) is None
        ), "Action2 should be deleted (solely reachable from Actions)"

        # Verify edges from agent and actions are deleted
        assert await Edge.get(edge_agent_actions.id) is None
        assert await Edge.get(edge_actions_action1.id) is None
        assert await Edge.get(edge_actions_action2.id) is None

    @pytest.mark.asyncio
    async def test_node_delete_cascade_preserves_shared_connections(self, temp_context):
        """Test cascade delete preserves nodes with connections to both deletion path and non-deletion path.

        This test verifies that:
        - A node connected to both the deletion path and an external node is preserved
        - Only nodes solely reachable from the deleted node are deleted
        """
        from jvspatial.core.context import set_default_context

        set_default_context(temp_context)

        # Create structure:
        # App -> Agents -> Agent -> Actions -> Action1 -> External
        #                              -> Action2 (solely connected, should be deleted)
        # Also: Agent -> Memory (solely connected, should be deleted)
        # Also: SharedNode -> Action1 (shared connection, Action1 should be preserved)
        app = await TestNode.create(name="App")
        agents = await TestNode.create(name="Agents")
        agent = await TestNode.create(name="Agent")
        actions = await TestNode.create(name="Actions")
        action1 = await TestNode.create(name="Action1")
        action2 = await TestNode.create(name="Action2")
        memory = await TestNode.create(name="Memory")
        external = await TestNode.create(name="External")
        shared_node = await TestNode.create(name="SharedNode")

        # Connect deletion path
        await app.connect(agents)
        await agents.connect(agent)
        await agent.connect(actions)
        edge_actions_action1 = await actions.connect(action1)
        edge_actions_action2 = await actions.connect(action2)
        edge_agent_memory = await agent.connect(memory)

        # Connect external node (Action1 -> External)
        edge_action1_external = await action1.connect(external)

        # Connect shared node (SharedNode -> Action1)
        # This creates a connection from outside the deletion path to Action1
        edge_shared_action1 = await shared_node.connect(action1)

        # Store IDs for verification
        app_id = app.id
        agents_id = agents.id
        agent_id = agent.id
        actions_id = actions.id
        action1_id = action1.id
        action2_id = action2.id
        memory_id = memory.id
        external_id = external.id
        shared_node_id = shared_node.id

        # Delete agent with cascade
        await agent.delete(cascade=True)

        # Verify agent is deleted
        assert await TestNode.get(agent_id) is None

        # Verify ancestors are preserved
        assert await TestNode.get(app_id) is not None, "App should be preserved"
        assert await TestNode.get(agents_id) is not None, "Agents should be preserved"

        # Verify Memory is deleted (solely reachable from Agent)
        assert await TestNode.get(memory_id) is None, "Memory should be deleted"

        # Verify Action1 is PRESERVED (has connection to SharedNode, which is outside deletion path)
        # Action1 is reachable from Agent, but it has a connection to SharedNode (not reachable from Agent)
        # This external connection prevents Action1 from being deleted
        action1_retrieved = await TestNode.get(action1_id)
        assert (
            action1_retrieved is not None
        ), "Action1 should be preserved (has external connection via SharedNode)"
        # Verify Action1 still has connection to SharedNode
        assert (
            edge_shared_action1.id in action1_retrieved.edge_ids
        ), "Action1 should still have edge to SharedNode"
        # Since Actions is also preserved (due to Action1's external connection), the edge from Actions to Action1 remains
        assert (
            edge_actions_action1.id in action1_retrieved.edge_ids
        ), "Edge Actions->Action1 should remain (Actions is preserved)"

        # Verify Actions and Action2 behavior
        # Current behavior: Because Action1 has an external connection (to SharedNode),
        # the recursive check determines that Action1 won't be deleted. This causes
        # Actions (parent of Action1) to also not be deleted, and consequently Action2
        # (sibling of Action1, also child of Actions) is also preserved.
        #
        # This is a limitation: ideally, Actions and Action2 should be deleted
        # (they're only reachable FROM Agent), while Action1 should be preserved
        # (has external connection). However, the current recursive check prevents
        # this by requiring all neighbors to be in the deletion set.
        actions_retrieved = await TestNode.get(actions_id)
        action2_retrieved = await TestNode.get(action2_id)

        # Current behavior: Actions and Action2 are preserved when Action1 has external connections
        assert (
            actions_retrieved is not None
        ), "Actions is preserved when Action1 has external connections (current behavior)"
        assert (
            action2_retrieved is not None
        ), "Action2 is preserved when Actions is preserved (current behavior)"

        # Verify edges are cleaned up properly
        # Since Actions is preserved, edges from Actions remain
        assert (
            edge_actions_action1.id in action1_retrieved.edge_ids
        ), "Edge Actions->Action1 should remain (Actions preserved)"
        assert (
            edge_actions_action2.id in action2_retrieved.edge_ids
        ), "Edge Actions->Action2 should remain (Actions preserved)"

        # Verify External is preserved (connected to Action1 which is preserved)
        assert (
            await TestNode.get(external_id) is not None
        ), "External should be preserved"

        # Verify SharedNode is preserved (outside deletion path)
        shared_node_retrieved = await TestNode.get(shared_node_id)
        assert shared_node_retrieved is not None, "SharedNode should be preserved"
        assert (
            edge_shared_action1.id in shared_node_retrieved.edge_ids
        ), "SharedNode should still have edge to Action1"

        # Verify edge from Action1 to External is preserved
        assert (
            await Edge.get(edge_action1_external.id) is not None
        ), "Edge Action1->External should be preserved"

        # Verify edges from deletion path
        # Edge Actions->Action1: Since Actions is preserved, this edge may still exist
        # but should be removed from Action1's edge_ids (already verified above)
        # Edge Actions->Action2: Since both Actions and Action2 are preserved, this edge should still exist
        # Edge Agent->Memory: Should be deleted since Memory is deleted
        assert (
            await Edge.get(edge_agent_memory.id) is None
        ), "Edge Agent->Memory should be deleted"


class TestContextDeleteDelegation:
    """Test GraphContext.delete() delegation to Node.delete() for nodes."""

    @pytest.fixture
    def temp_context(self):
        """Create temporary context for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import uuid

            unique_path = f"{tmpdir}/test_{uuid.uuid4().hex}"
            config = {"db_type": "json", "db_config": {"base_path": unique_path}}
            database = create_database(config["db_type"], **config["db_config"])
            context = GraphContext(database=database)
            yield context

    @pytest.mark.asyncio
    async def test_context_delete_node_delegates_to_node_delete(self, temp_context):
        """Test that context.delete(node) delegates to node.delete()."""
        from jvspatial.core.context import set_default_context

        # Set temp_context as default so entity methods use the same context
        set_default_context(temp_context)

        # Create node with edges
        node = await TestNode.create(name="test")
        child = await TestNode.create(name="child")
        edge = await node.connect(child)

        # Delete via context.delete() with cascade
        await temp_context.delete(node, cascade=True)

        # Verify node is deleted (use temp_context.get() to ensure same context)
        node_retrieved = await temp_context.get(TestNode, node.id)
        assert node_retrieved is None

        # Verify edge is deleted (cascade worked)
        edge_retrieved = await temp_context.get(Edge, edge.id)
        assert edge_retrieved is None

        # Verify child is deleted (solely connected to node, cascade worked)
        child_retrieved = await temp_context.get(TestNode, child.id)
        assert child_retrieved is None

    @pytest.mark.asyncio
    async def test_context_delete_node_no_cascade(self, temp_context):
        """Test that context.delete(node, cascade=False) works correctly."""
        # Create node with edges
        node = await TestNode.create(name="test")
        child = await TestNode.create(name="child")
        edge = await node.connect(child)

        # Delete via context.delete() without cascade
        await temp_context.delete(node, cascade=False)

        # Verify node is deleted
        assert await TestNode.get(node.id) is None

        # Verify edge is deleted (edges are always deleted)
        assert await Edge.get(edge.id) is None

        # Verify child is preserved (no cascade)
        child_retrieved = await TestNode.get(child.id)
        assert child_retrieved is not None
        assert edge.id not in child_retrieved.edge_ids

    @pytest.mark.asyncio
    async def test_context_delete_object_simple(self, temp_context):
        """Test that context.delete(object) performs simple deletion."""
        from jvspatial.core.context import set_default_context

        # Set temp_context as default so Object.get() uses the same context
        set_default_context(temp_context)

        # Create object
        obj = await TestObject.create(name="test", value=42)
        obj_id = obj.id

        # Delete via context.delete()
        await temp_context.delete(obj)

        # Verify object is deleted (use temp_context.get() to ensure same context)
        obj_retrieved = await temp_context.get(TestObject, obj_id)
        assert obj_retrieved is None

    @pytest.mark.asyncio
    async def test_context_delete_edge_simple(self, temp_context):
        """Test that context.delete(edge) performs simple deletion."""
        from jvspatial.core.context import set_default_context

        # Set temp_context as default so Edge.get() uses the same context
        set_default_context(temp_context)

        # Create nodes and edge
        node1 = await TestNode.create(name="node1")
        node2 = await TestNode.create(name="node2")
        edge = await TestEdge.create(source=node1.id, target=node2.id, weight=5)
        edge_id = edge.id

        # Delete via context.delete()
        await temp_context.delete(edge)

        # Verify edge is deleted (use temp_context.get() to ensure same context)
        edge_retrieved = await temp_context.get(TestEdge, edge_id)
        assert edge_retrieved is None
