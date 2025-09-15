"""
Enhanced unit tests for Walker class covering @on_exit hooks,
pause/resume, error handling, and complex traversals.
"""

from collections import deque
from typing import List

import pytest

from jvspatial.core.entities import (
    Edge,
    Node,
    Root,
    TraversalPaused,
    Walker,
    find_subclass_by_name,
    on_exit,
    on_visit,
)


class WalkerTestNode(Node):
    """Test node for walker testing"""

    name: str = "WalkerTestNode"
    visited: bool = False


class City(Node):
    """Test city node"""

    name: str
    population: int = 0


class Agent(Node):
    """Test agent node"""

    name: str
    status: str = "active"


class TestWalkerBasics:
    """Test basic walker functionality"""

    @pytest.mark.asyncio
    async def test_walker_initialization(self):
        """Test walker initialization and ID generation"""
        walker = Walker()

        assert walker.id.startswith("w:Walker:")
        assert isinstance(walker.queue, deque)
        assert isinstance(walker.response, dict)
        assert walker.current_node is None
        assert walker.paused == False

    @pytest.mark.asyncio
    async def test_custom_walker_initialization(self):
        """Test custom walker with properties"""

        class CustomWalker(Walker):
            name: str = "TestWalker"
            priority: int = 1

        walker = CustomWalker(name="MyWalker", priority=5)

        assert walker.name == "MyWalker"
        assert walker.priority == 5
        assert walker.id.startswith("w:CustomWalker:")

    @pytest.mark.asyncio
    async def test_walker_spawn_default_root(self):
        """Test walker spawning with default root node"""

        class SimpleWalker(Walker):
            @on_visit(Root)
            async def on_root(self, here):
                self.response["visited_root"] = True

        walker = SimpleWalker()
        result = await walker.spawn()

        assert result == walker
        assert walker.response.get("visited_root") == True

    @pytest.mark.asyncio
    async def test_walker_spawn_custom_start(self):
        """Test walker spawning with custom start node"""

        class TestWalker(Walker):
            @on_visit(WalkerTestNode)
            async def on_test_node(self, here):
                self.response["visited_test"] = here.name

        start_node = await WalkerTestNode.create(name="StartNode")
        walker = TestWalker()
        result = await walker.spawn(start=start_node)

        assert walker.response.get("visited_test") == "StartNode"


class TestWalkerHooks:
    """Test walker hook system"""

    @pytest.mark.asyncio
    async def test_on_visit_specific_node_type(self):
        """Test @on_visit for specific node types"""

        class CityWalker(Walker):
            cities_visited: List[str] = []

            @on_visit(City)
            async def visit_city(self, here):
                self.cities_visited.append(here.name)
                self.response["city_count"] = len(self.cities_visited)

        chicago = await City.create(name="Chicago", population=2697000)
        walker = CityWalker()
        await walker.spawn(start=chicago)

        assert "Chicago" in walker.cities_visited
        assert walker.response.get("city_count") == 1

    @pytest.mark.asyncio
    async def test_on_visit_multiple_node_types(self):
        """Test walker with multiple @on_visit hooks"""

        class MultiWalker(Walker):
            @on_visit(City)
            async def visit_city(self, here):
                self.response["visited_city"] = here.name

            @on_visit(Agent)
            async def visit_agent(self, here):
                self.response["visited_agent"] = here.name

            @on_visit(WalkerTestNode)
            async def visit_test_node(self, here):
                self.response["visited_test"] = here.name

        city = await City.create(name="Boston")
        walker = MultiWalker()
        await walker.spawn(start=city)

        assert walker.response.get("visited_city") == "Boston"
        assert "visited_agent" not in walker.response
        assert "visited_test" not in walker.response

    @pytest.mark.asyncio
    async def test_on_exit_hook(self):
        """Test @on_exit hook execution"""

        class ExitWalker(Walker):
            @on_visit(WalkerTestNode)
            async def visit_node(self, here):
                self.response["visited"] = here.name

            @on_exit
            async def on_completion(self):
                self.response["completed"] = True
                self.response["exit_time"] = "test_time"

        node = await WalkerTestNode.create(name="ExitTest")
        walker = ExitWalker()
        await walker.spawn(start=node)

        assert walker.response.get("visited") == "ExitTest"
        assert walker.response.get("completed") == True
        assert walker.response.get("exit_time") == "test_time"

    @pytest.mark.asyncio
    async def test_multiple_on_exit_hooks(self):
        """Test multiple @on_exit hooks"""

        class MultiExitWalker(Walker):
            @on_exit
            async def first_exit(self):
                if "exit_order" not in self.response:
                    self.response["exit_order"] = []
                self.response["exit_order"].append("first")

            @on_exit
            async def second_exit(self):
                if "exit_order" not in self.response:
                    self.response["exit_order"] = []
                self.response["exit_order"].append("second")

        walker = MultiExitWalker()
        await walker.spawn()

        assert "exit_order" in walker.response
        assert len(walker.response["exit_order"]) == 2

    @pytest.mark.asyncio
    async def test_sync_hooks(self):
        """Test synchronous hook functions"""

        class SyncWalker(Walker):
            @on_visit(WalkerTestNode)
            def sync_visit(self, here):  # Not async
                self.response["sync_visited"] = here.name

            @on_exit
            def sync_exit(self):  # Not async
                self.response["sync_completed"] = True

        node = await WalkerTestNode.create(name="SyncTest")
        walker = SyncWalker()
        await walker.spawn(start=node)

        assert walker.response.get("sync_visited") == "SyncTest"
        assert walker.response.get("sync_completed") == True


class TestWalkerTraversal:
    """Test walker traversal patterns"""

    @pytest.mark.asyncio
    async def test_simple_traversal(self):
        """Test simple node-to-node traversal"""

        class TraversalWalker(Walker):
            @on_visit(WalkerTestNode)
            async def visit_node(self, here):
                if "visited_nodes" not in self.response:
                    self.response["visited_nodes"] = []
                self.response["visited_nodes"].append(here.name)

                # Visit connected nodes
                connected_nodes = await (await here.nodes()).filter()
                for node in connected_nodes:
                    if node.name not in self.response["visited_nodes"]:
                        await self.visit(node)

        # Create connected nodes
        node_a = await WalkerTestNode.create(name="NodeA")
        node_b = await WalkerTestNode.create(name="NodeB")
        node_c = await WalkerTestNode.create(name="NodeC")

        await node_a.connect(node_b)
        await node_b.connect(node_c)

        walker = TraversalWalker()
        await walker.spawn(start=node_a)

        visited = walker.response.get("visited_nodes", [])
        assert "NodeA" in visited
        assert "NodeB" in visited
        assert "NodeC" in visited

    @pytest.mark.asyncio
    async def test_breadth_first_traversal(self):
        """Test breadth-first traversal pattern"""

        class BFSWalker(Walker):
            @on_visit(WalkerTestNode)
            async def visit_node(self, here):
                if "visit_order" not in self.response:
                    self.response["visit_order"] = []
                self.response["visit_order"].append(here.name)

                # Add all unvisited neighbors to queue
                connected_nodes = await (await here.nodes()).filter()
                unvisited = [
                    n
                    for n in connected_nodes
                    if n.name not in self.response["visit_order"]
                ]
                await self.visit(unvisited)

        # Create tree structure
        root = await WalkerTestNode.create(name="Root")
        child1 = await WalkerTestNode.create(name="Child1")
        child2 = await WalkerTestNode.create(name="Child2")
        grandchild1 = await WalkerTestNode.create(name="GrandChild1")
        grandchild2 = await WalkerTestNode.create(name="GrandChild2")

        await root.connect(child1)
        await root.connect(child2)
        await child1.connect(grandchild1)
        await child2.connect(grandchild2)

        walker = BFSWalker()
        await walker.spawn(start=root)

        visit_order = walker.response.get("visit_order", [])
        assert visit_order[0] == "Root"
        # Children should be visited before grandchildren
        child1_idx = visit_order.index("Child1")
        child2_idx = visit_order.index("Child2")
        grandchild1_idx = visit_order.index("GrandChild1")
        grandchild2_idx = visit_order.index("GrandChild2")

        assert child1_idx < grandchild1_idx
        assert child2_idx < grandchild2_idx

    @pytest.mark.asyncio
    async def test_visit_method(self):
        """Test the visit method for adding nodes to queue"""
        walker = Walker()

        node1 = await WalkerTestNode.create(name="Node1")
        node2 = await WalkerTestNode.create(name="Node2")
        node3 = await WalkerTestNode.create(name="Node3")

        # Test visiting single node
        result = await walker.visit(node1)
        assert result == [node1]
        assert node1 in walker.queue

        # Test visiting multiple nodes
        result = await walker.visit([node2, node3])
        assert result == [node2, node3]
        assert node2 in walker.queue
        assert node3 in walker.queue

        # Check queue order
        assert len(walker.queue) == 3


class TestWalkerPauseResume:
    """Test walker pause and resume functionality"""

    @pytest.mark.asyncio
    async def test_walker_pause(self):
        """Test pausing walker traversal"""

        class PausableWalker(Walker):
            visit_count: int = 0

            @on_visit(WalkerTestNode)
            async def visit_node(self, here):
                self.visit_count += 1
                if "visited" not in self.response:
                    self.response["visited"] = []
                self.response["visited"].append(here.name)

                # Pause after visiting 2 nodes
                if self.visit_count >= 2:
                    self.paused = True
                else:
                    # Add more nodes to visit
                    connected_nodes = await (await here.nodes()).filter()
                    await self.visit(connected_nodes)

        # Create chain of nodes
        node1 = await WalkerTestNode.create(name="Node1")
        node2 = await WalkerTestNode.create(name="Node2")
        node3 = await WalkerTestNode.create(name="Node3")

        await node1.connect(node2)
        await node2.connect(node3)

        walker = PausableWalker()
        await walker.spawn(start=node1)

        # Should be paused after 2 visits
        assert walker.paused == True
        assert walker.visit_count == 2
        assert len(walker.response.get("visited", [])) == 2

    @pytest.mark.asyncio
    async def test_walker_resume(self):
        """Test resuming paused walker"""

        class ResumableWalker(Walker):
            visit_count: int = 0

            @on_visit(WalkerTestNode)
            async def visit_node(self, here):
                self.visit_count += 1
                if "visited" not in self.response:
                    self.response["visited"] = []
                self.response["visited"].append(here.name)

                # Pause after first visit
                if self.visit_count == 1:
                    self.paused = True
                    # Add more work to queue
                    connected_nodes = await (await here.nodes()).filter()
                    await self.visit(connected_nodes)

        node1 = await WalkerTestNode.create(name="Node1")
        node2 = await WalkerTestNode.create(name="Node2")
        await node1.connect(node2)

        walker = ResumableWalker()
        await walker.spawn(start=node1)

        # Should be paused after 1 visit
        assert walker.paused == True
        assert walker.visit_count == 1

        # Resume and check completion
        await walker.resume()
        assert walker.paused == False
        assert walker.visit_count >= 2


class TestWalkerErrorHandling:
    """Test walker error handling"""

    @pytest.mark.asyncio
    async def test_hook_error_handling(self):
        """Test error handling in hooks"""

        class ErrorWalker(Walker):
            @on_visit(WalkerTestNode)
            async def visit_with_error(self, here):
                if here.name == "ErrorNode":
                    raise ValueError("Test error")
                self.response["visited"] = here.name

            @on_exit
            async def exit_hook(self):
                self.response["completed"] = True

        # Test with normal node
        normal_node = await WalkerTestNode.create(name="NormalNode")
        walker = ErrorWalker()
        await walker.spawn(start=normal_node)

        assert walker.response.get("visited") == "NormalNode"
        assert walker.response.get("completed") == True

    @pytest.mark.asyncio
    async def test_traversal_error_handling(self):
        """Test error handling during traversal"""

        class CrashWalker(Walker):
            @on_visit(WalkerTestNode)
            async def visit_node(self, here):
                # This will cause an error in spawning
                raise RuntimeError("Traversal error")

        node = await WalkerTestNode.create(name="CrashNode")
        walker = CrashWalker()
        result = await walker.spawn(start=node)

        # Walker should handle the error and set response
        assert result == walker
        assert "status" in walker.response
        assert walker.response["status"] == 500

    @pytest.mark.asyncio
    async def test_exit_hook_after_error(self):
        """Test that exit hooks run even after errors"""

        class ErrorExitWalker(Walker):
            @on_visit(WalkerTestNode)
            async def visit_node(self, here):
                raise ValueError("Visit error")

            @on_exit
            async def exit_hook(self):
                self.response["exit_called"] = True

        node = await WalkerTestNode.create(name="ErrorNode")
        walker = ErrorExitWalker()
        await walker.spawn(start=node)

        # Exit hook should still be called
        assert walker.response.get("exit_called") == True


class TestWalkerVisitingContext:
    """Test walker visiting context manager"""

    @pytest.mark.asyncio
    async def test_visiting_context(self):
        """Test the visiting context manager"""
        walker = Walker()
        node = await WalkerTestNode.create(name="ContextNode")

        # Before visiting
        assert walker.current_node is None
        assert walker.here is None
        assert node.visitor is None

        # During visiting
        with walker.visiting(node):
            assert walker.current_node == node
            assert walker.here == node
            assert node.visitor == walker

        # After visiting
        assert walker.current_node is None
        assert walker.here is None
        assert node.visitor is None

    @pytest.mark.asyncio
    async def test_visitor_property(self):
        """Test walker visitor property"""
        walker = Walker()

        # Visitor should return self
        assert walker.visitor == walker


class TestWalkerNodeQueries:
    """Test walker node query functionality"""

    @pytest.mark.asyncio
    async def test_walker_nodes_method(self):
        """Test walker's nodes() method"""

        class QueryWalker(Walker):
            @on_visit(WalkerTestNode)
            async def visit_node(self, here):
                # Get connected nodes
                connected = await self.nodes()
                self.response["connected_count"] = len(connected.nodes)

                # Get outbound connections only
                outbound = await self.nodes(direction="out")
                self.response["outbound_count"] = len(outbound.nodes)

        node1 = await WalkerTestNode.create(name="Node1")
        node2 = await WalkerTestNode.create(name="Node2")
        node3 = await WalkerTestNode.create(name="Node3")

        await node1.connect(node2, direction="out")
        await node3.connect(node1, direction="out")  # node3 -> node1

        walker = QueryWalker()
        await walker.spawn(start=node1)

        assert walker.response.get("connected_count") == 2
        assert walker.response.get("outbound_count") == 1

    @pytest.mark.asyncio
    async def test_walker_nodes_no_current_node(self):
        """Test walker nodes() method when no current node"""
        walker = Walker()

        # Should return empty NodeQuery
        query = await walker.nodes()
        assert len(query.nodes) == 0
        assert query.source is None


class TestWalkerHookRegistration:
    """Test walker hook registration system"""

    def test_hook_registration_on_subclass(self):
        """Test that hooks are registered when subclass is created"""

        class HookedWalker(Walker):
            @on_visit(WalkerTestNode)
            async def visit_test(self, here):
                pass

            @on_visit(City)
            async def visit_city(self, here):
                pass

        # Check that hooks are registered
        assert WalkerTestNode in HookedWalker._visit_hooks
        assert City in HookedWalker._visit_hooks

        # Check hook functions
        test_hook = HookedWalker._visit_hooks[WalkerTestNode]
        city_hook = HookedWalker._visit_hooks[City]

        assert test_hook.__name__ == "visit_test"
        assert city_hook.__name__ == "visit_city"

    def test_hook_inheritance(self):
        """Test hook inheritance in walker subclasses"""

        class BaseWalker(Walker):
            @on_visit(WalkerTestNode)
            async def base_visit(self, here):
                pass

        class DerivedWalker(BaseWalker):
            @on_visit(City)
            async def derived_visit(self, here):
                pass

        # Derived walker should have both hooks
        assert WalkerTestNode in DerivedWalker._visit_hooks
        assert City in DerivedWalker._visit_hooks


class TestWalkerIdGeneration:
    """Test walker ID generation"""

    def test_automatic_id_generation(self):
        """Test automatic ID generation for walkers"""
        walker = Walker()
        assert walker.id.startswith("w:Walker:")

        class CustomWalker(Walker):
            pass

        custom_walker = CustomWalker()
        assert custom_walker.id.startswith("w:CustomWalker:")

    def test_explicit_id_setting(self):
        """Test setting explicit walker ID"""
        custom_id = "w:Walker:custom123"
        walker = Walker(id=custom_id)
        assert walker.id == custom_id
