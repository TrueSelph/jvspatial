"""Test class-aware get() method behavior.

Ensures that Entity.get() only returns instances of the requested class,
not instances of other classes even if they share the same type_code.
"""

import pytest

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities import Node, Object
from jvspatial.db.jsondb import JsonDB


class TestClassAwareGet:
    """Test class-aware get() method."""

    @pytest.fixture
    async def temp_context(self):
        """Create temporary context for testing."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            jsondb = JsonDB(base_path=tmpdir)
            ctx = GraphContext(database=jsondb)
            set_default_context(ctx)
            yield ctx

    @pytest.mark.asyncio
    async def test_node_get_returns_only_requested_class(self, temp_context):
        """Test that Node.get() only returns instances of the requested Node subclass."""

        class Agent(Node):
            name: str = ""

        class Action(Node):
            name: str = ""

        # Create entities
        agent = await Agent.create(name="test_agent")
        action = await Action.create(name="test_action")
        await temp_context.save(agent)
        await temp_context.save(action)

        # Agent.get() with action ID should return None
        result = await Agent.get(action.id)
        assert result is None, "Agent.get() should return None for Action ID"

        # Action.get() with agent ID should return None
        result = await Action.get(agent.id)
        assert result is None, "Action.get() should return None for Agent ID"

        # Agent.get() with agent ID should return Agent
        result = await Agent.get(agent.id)
        assert result is not None, "Agent.get() should return Agent for its own ID"
        assert isinstance(result, Agent), f"Expected Agent, got {type(result)}"
        assert result.id == agent.id, "Returned agent should have correct ID"

        # Action.get() with action ID should return Action
        result = await Action.get(action.id)
        assert result is not None, "Action.get() should return Action for its own ID"
        assert isinstance(result, Action), f"Expected Action, got {type(result)}"
        assert result.id == action.id, "Returned action should have correct ID"

    @pytest.mark.asyncio
    async def test_object_get_returns_only_requested_class(self, temp_context):
        """Test that Object.get() only returns instances of the requested Object subclass."""

        class User(Object):
            email: str = ""

        class Config(Object):
            key: str = ""

        # Create entities
        user = await User.create(email="user@example.com")
        config = await Config.create(key="test_key")
        await temp_context.save(user)
        await temp_context.save(config)

        # User.get() with config ID should return None
        result = await User.get(config.id)
        assert result is None, "User.get() should return None for Config ID"

        # Config.get() with user ID should return None
        result = await Config.get(user.id)
        assert result is None, "Config.get() should return None for User ID"

        # User.get() with user ID should return User
        result = await User.get(user.id)
        assert result is not None, "User.get() should return User for its own ID"
        assert isinstance(result, User), f"Expected User, got {type(result)}"
        assert result.id == user.id, "Returned user should have correct ID"

        # Config.get() with config ID should return Config
        result = await Config.get(config.id)
        assert result is not None, "Config.get() should return Config for its own ID"
        assert isinstance(result, Config), f"Expected Config, got {type(result)}"
        assert result.id == config.id, "Returned config should have correct ID"

    @pytest.mark.asyncio
    async def test_get_with_wrong_type_code_returns_none(self, temp_context):
        """Test that get() returns None when type_code doesn't match."""

        class TestNode(Node):
            name: str = ""

        class TestObject(Object):
            name: str = ""

        # Create entities
        node = await TestNode.create(name="test_node")
        obj = await TestObject.create(name="test_object")
        await temp_context.save(node)
        await temp_context.save(obj)

        # Node.get() with Object ID should return None (different type_code)
        result = await TestNode.get(obj.id)
        assert result is None, "Node.get() should return None for Object ID"

        # Object.get() with Node ID should return None (different type_code)
        result = await TestObject.get(node.id)
        assert result is None, "Object.get() should return None for Node ID"

    @pytest.mark.asyncio
    async def test_get_with_subclass_returns_subclass(self, temp_context):
        """Test that get() returns subclass instances when requested."""

        class BaseNode(Node):
            name: str = ""

        class DerivedNode(BaseNode):
            value: int = 0

        # Create derived node
        derived = await DerivedNode.create(name="derived", value=42)
        await temp_context.save(derived)

        # BaseNode.get() should return DerivedNode (subclass)
        result = await BaseNode.get(derived.id)
        assert result is not None, "BaseNode.get() should return DerivedNode"
        assert isinstance(result, DerivedNode), "Should return DerivedNode instance"
        assert result.value == 42, "Should have subclass properties"

        # DerivedNode.get() should return DerivedNode
        result = await DerivedNode.get(derived.id)
        assert result is not None, "DerivedNode.get() should return DerivedNode"
        assert isinstance(result, DerivedNode), "Should return DerivedNode instance"

    # -------------------------------------------------------------------------
    # Ghost node tests — entity class module not imported
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_node_get_returns_base_instance_for_ghost_node(self, temp_context):
        """Node.get() returns a Node base instance when the stored entity class is unknown.

        A ghost node is a record whose 'entity' field names a class that is not
        currently imported (e.g. an action whose module was removed).
        Node.get() should return a Node base-class instance so that callers
        can call node.delete(cascade=True) through the standard interface.
        """
        from jvspatial.core.context import get_default_context
        from jvspatial.core.entities.node import Node as _Node

        context = get_default_context()
        type_code = context._get_entity_type_code(_Node)
        collection = context._get_collection_name(type_code)

        ghost_id = "ghost-node-test-id"
        ghost_record = {
            "id": ghost_id,
            "entity": "NeverImportedClass",
            "context": {
                "name": "ghost",
                "enabled": True,
            },
            "edges": [],
        }
        await context.database.save(collection, ghost_record)

        result = await _Node.get(ghost_id)
        assert result is not None, (
            "Node.get() must return a Node instance for a ghost record "
            "(entity class not imported), not None"
        )
        assert isinstance(result, _Node), f"Expected Node instance, got {type(result)}"
        assert result.id == ghost_id

    @pytest.mark.asyncio
    async def test_node_get_still_rejects_cross_hierarchy_ids(self, temp_context):
        """Node subclass.get() still returns None for a sibling-hierarchy id.

        Agent.get(action_id) must return None even after the ghost-node fallback
        is in place, because the Action class IS imported and is not a subclass
        of Agent.
        """

        class AgentNode(Node):
            name: str = ""

        class ActionNode(Node):
            name: str = ""

        agent = await AgentNode.create(name="agent")
        action = await ActionNode.create(name="action")

        # Cross-hierarchy: AgentNode.get() on an ActionNode id
        result = await AgentNode.get(action.id)
        assert result is None, (
            "AgentNode.get() must return None for an ActionNode id "
            "(cross-hierarchy call must still be rejected)"
        )

        # Cross-hierarchy: ActionNode.get() on an AgentNode id
        result = await ActionNode.get(agent.id)
        assert result is None, "ActionNode.get() must return None for an AgentNode id"

    @pytest.mark.asyncio
    async def test_ghost_node_delete_removes_node_and_edges(self, temp_context):
        """Node.get() + node.delete(cascade=True) fully removes a ghost node and its edges.

        This is the end-to-end path used by applications that use class-aware
        get for graph cleanup when a node's class module is no longer imported.
        After deletion both the node record and any edge pointing to it must be
        absent from the database.
        """
        from jvspatial.core.context import get_default_context
        from jvspatial.core.entities.node import Node as _Node

        context = get_default_context()
        type_code = context._get_entity_type_code(_Node)
        collection = context._get_collection_name(type_code)

        # Create a real manager node that will hold an edge to the ghost
        class ManagerNode(Node):
            name: str = ""

        manager = await ManagerNode.create(name="manager")

        ghost_id = "ghost-delete-test-id"
        ghost_record = {
            "id": ghost_id,
            "entity": "AnotherNeverImportedClass",
            "context": {
                "name": "ghost",
                "entity_id": "test-entity",
            },
            "edges": [],
        }
        await context.database.save(collection, ghost_record)

        # Inject an edge from manager → ghost (as would exist in any graph app)
        edge_record = {
            "id": "ghost-delete-edge-id",
            "entity": "Edge",
            "source": manager.id,
            "target": ghost_id,
            "context": {},
        }
        await context.database.save("edge", edge_record)

        # Standard interface: get + delete
        ghost_node = await _Node.get(ghost_id)
        assert ghost_node is not None, "Node.get() must find the ghost node"
        await ghost_node.delete(cascade=True)

        # Node record must be gone
        raw_nodes = await context.database.find(collection, {"id": ghost_id})
        assert len(raw_nodes) == 0, "Ghost node record must be removed after delete"

        # Edge pointing to the ghost must be gone
        raw_edges = await context.database.find("edge", {"target": ghost_id})
        assert (
            len(raw_edges) == 0
        ), "Edge pointing to ghost node must be removed — no remnant edges"
