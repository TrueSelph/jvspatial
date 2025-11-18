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
        """Test node deletion removes outgoing edges."""
        # Create nodes
        parent = await TestNode.create(name="parent")
        child1 = await TestNode.create(name="child1")
        child2 = await TestNode.create(name="child2")

        # Create edges from parent to children
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

        # Verify edges are deleted
        assert await temp_context.get(Edge, edge1.id) is None
        assert await temp_context.get(Edge, edge2.id) is None

        # Verify edge_ids are removed from child nodes (children preserved)
        child1_retrieved = await temp_context.get(TestNode, child1.id)
        child2_retrieved = await temp_context.get(TestNode, child2.id)
        assert child1_retrieved is not None
        assert child2_retrieved is not None
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

        # Verify edge is deleted
        assert await temp_context.get(Edge, edge.id) is None

        # Verify edge_id is removed from child node (child preserved)
        child_retrieved = await temp_context.get(TestNode, child.id)
        assert child_retrieved is not None
        assert edge.id not in child_retrieved.edge_ids

    @pytest.mark.asyncio
    async def test_node_delete_with_bidirectional_edges(self, temp_context):
        """Test node deletion removes bidirectional edges."""
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

        # Verify edge is deleted
        assert await temp_context.get(Edge, edge.id) is None

        # Verify edge_id is removed from node2 (node2 preserved)
        node2_retrieved = await temp_context.get(TestNode, node2.id)
        assert node2_retrieved is not None
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

        # Verify edges from parent are deleted
        assert await temp_context.get(Edge, edge1.id) is None
        assert await temp_context.get(Edge, edge2.id) is None

        # child1 has edge1 (to parent) and edge3 (to grandchild)
        # When checking if child1 is solely connected to parent, we check if ALL edges connect to parent.
        # Since edge3 connects to grandchild (not parent), child1 is NOT solely connected.
        # So child1 should NOT be deleted when parent is deleted.
        # However, if we want to test cascade deletion of solely connected nodes,
        # we need child1 to be solely connected. So let's test a simpler structure:
        # Actually, the test name says "solely connected nodes", so let's test that:
        # child2 is solely connected (only has edge2 to parent), so it should be deleted.
        # child1 is NOT solely connected (has edge1 to parent AND edge3 to grandchild), so it should NOT be deleted.

        # Verify child1 is NOT deleted (has edge3 to grandchild, so not solely connected)
        child1_retrieved = await temp_context.get(TestNode, child1.id)
        assert (
            child1_retrieved is not None
        ), "child1 should be preserved (has edge3 to grandchild)"

        # Verify child2 is deleted (solely connected to parent via edge2)
        assert await temp_context.get(TestNode, child2.id) is None

        # Verify grandchild is preserved (child1 was not deleted, so grandchild remains)
        grandchild_retrieved = await temp_context.get(TestNode, grandchild.id)
        assert grandchild_retrieved is not None

        # Verify edge3 is preserved (child1 was not deleted)
        edge3_retrieved = await temp_context.get(Edge, edge3.id)
        assert edge3_retrieved is not None

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

        # Verify edges are deleted
        assert await Edge.get(edge1.id) is None
        assert await Edge.get(edge2.id) is None

        # Verify child nodes are preserved (not cascaded)
        child1_retrieved = await TestNode.get(child1.id)
        child2_retrieved = await TestNode.get(child2.id)
        assert child1_retrieved is not None
        assert child2_retrieved is not None
        assert edge1.id not in child1_retrieved.edge_ids
        assert edge2.id not in child2_retrieved.edge_ids

    @pytest.mark.asyncio
    async def test_node_delete_cascade_preserves_shared_nodes(self, temp_context):
        """Test node deletion with cascade preserves nodes connected to other nodes."""
        # Create nodes: parent -> child1 -> shared
        #                      -> child2 -> shared
        parent = await TestNode.create(name="parent")
        child1 = await TestNode.create(name="child1")
        child2 = await TestNode.create(name="child2")
        shared = await TestNode.create(name="shared")

        # Connect them
        edge1 = await parent.connect(child1)
        edge2 = await parent.connect(child2)
        edge3 = await child1.connect(shared)
        edge4 = await child2.connect(shared)

        # Delete parent with cascade
        await parent.delete(cascade=True)

        # Verify parent is deleted
        assert await TestNode.get(parent.id) is None

        # Verify edges from parent are deleted
        assert await Edge.get(edge1.id) is None
        assert await Edge.get(edge2.id) is None

        # child1 has edge1 (to parent) and edge3 (to shared)
        # After edge1 is removed, child1 still has edge3, so it's NOT solely connected
        # Therefore, child1 should be preserved
        child1_retrieved = await TestNode.get(child1.id)
        assert child1_retrieved is not None
        assert edge1.id not in child1_retrieved.edge_ids
        assert edge3.id in child1_retrieved.edge_ids

        # child2 has edge2 (to parent) and edge4 (to shared)
        # After edge2 is removed, child2 still has edge4, so it's NOT solely connected
        # Therefore, child2 should be preserved
        child2_retrieved = await TestNode.get(child2.id)
        assert child2_retrieved is not None
        assert edge2.id not in child2_retrieved.edge_ids
        assert edge4.id in child2_retrieved.edge_ids

        # Verify shared node is preserved
        shared_retrieved = await TestNode.get(shared.id)
        assert shared_retrieved is not None

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

        # Verify edges from/to node_a are deleted
        assert await Edge.get(edge_ab.id) is None
        assert await Edge.get(edge_ad.id) is None

        # Verify node_b is deleted (solely connected to node_a via edge_ab)
        # Wait, node_b also has edge_bc and edge_bd, so it's not solely connected
        # Actually, after edge_ab is removed, node_b still has edge_bc and edge_bd,
        # so it should be preserved
        node_b_retrieved = await TestNode.get(node_b.id)
        # node_b should be preserved because it has other connections
        assert node_b_retrieved is not None
        assert edge_ab.id not in node_b_retrieved.edge_ids
        assert edge_bc.id in node_b_retrieved.edge_ids
        assert edge_bd.id in node_b_retrieved.edge_ids

        # Verify node_d is preserved (has edge_de and edge_bd)
        node_d_retrieved = await TestNode.get(node_d.id)
        assert node_d_retrieved is not None
        assert edge_ad.id not in node_d_retrieved.edge_ids
        assert edge_de.id in node_d_retrieved.edge_ids
        assert edge_bd.id in node_d_retrieved.edge_ids


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
