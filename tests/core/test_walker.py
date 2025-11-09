"""
Test suite for Walker functionality and core entities.

This module implements comprehensive tests for:
- Walker subclass creation and inheritance
- @on_visit and @on_exit decorators
- Control methods: skip(), pause(), resume(), disengage()
- Walker queue behavior and traversal
- Walker lifecycle and error handling
- Integration with Node visitation patterns
"""

import asyncio
import weakref
from collections import deque
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import Field

from jvspatial.core import on_exit, on_visit
from jvspatial.core.entities import (
    Edge,
    Node,
    Root,
    Walker,
)
from jvspatial.exceptions import JVSpatialError, WalkerError


# Define traversal exceptions for testing
class TraversalPaused(JVSpatialError):
    """Exception raised when traversal is paused."""

    pass


class TraversalSkipped(JVSpatialError):
    """Exception raised when traversal is skipped."""

    pass


class WalkerTestNode(Node):
    """Test node for walker testing."""

    name: str = ""
    value: int = 0
    category: str = ""


class WalkerTestEdge(Edge):
    """Test edge for walker testing."""

    weight: int = 1
    condition: str = "good"


class WalkerTestWalker(Walker):
    """Test walker for basic functionality."""

    visited_nodes: List[str] = Field(default_factory=list)
    visited_edges: List[str] = Field(default_factory=list)
    exit_called: bool = Field(default=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @on_visit(WalkerTestNode)
    async def visit_test_node(self, here):
        """Visit hook for TestNode."""
        self.visited_nodes.append(here.name)

    @on_visit(WalkerTestEdge)
    async def visit_test_edge(self, here):
        """Visit hook for TestEdge."""
        self.visited_edges.append(here.id)

    @on_exit
    async def on_walker_exit(self):
        """Exit hook for walker."""
        self.exit_called = True


class SkippingWalker(Walker):
    """Test walker that uses skip() functionality."""

    visited_nodes: List[str] = Field(default_factory=list)
    skipped_nodes: List[str] = Field(default_factory=list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @on_visit(WalkerTestNode)
    async def visit_with_skip(self, here):
        """Visit hook that conditionally skips nodes."""
        if here.name.startswith("skip"):
            self.skipped_nodes.append(here.name)
            await self.skip()  # This should prevent further processing
            # This line should not be reached
            self.visited_nodes.append("SHOULD_NOT_REACH")
        else:
            self.visited_nodes.append(here.name)


class PausingWalker(Walker):
    """Test walker that uses pause() functionality."""

    visited_nodes: List[str] = Field(default_factory=list)
    pause_after: Optional[str] = Field(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @on_visit(WalkerTestNode)
    async def visit_with_pause(self, here):
        """Visit hook that conditionally pauses traversal."""
        self.visited_nodes.append(here.name)
        if self.pause_after and here.name == self.pause_after:
            self.pause(f"Pausing after {here.name}")


class ControlFlowWalker(Walker):
    """Walker for testing various control flow methods."""

    events: List[str] = Field(default_factory=list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @on_visit(WalkerTestNode)
    async def track_visits(self, here):
        """Track all node visits."""
        self.events.append(f"visited:{here.name}")

    @on_exit
    async def track_exit(self):
        """Track walker exit."""
        self.events.append("exit:called")


@pytest.fixture
def mock_context():
    """Mock GraphContext for testing."""
    context = MagicMock()
    context.database = AsyncMock()
    return context


@pytest.fixture
async def test_nodes():
    """Create test nodes for walker testing."""
    nodes = [
        WalkerTestNode(name="node1", value=10, category="A"),
        WalkerTestNode(name="node2", value=20, category="B"),
        WalkerTestNode(name="skip_node", value=30, category="A"),
        WalkerTestNode(name="node4", value=40, category="C"),
    ]
    return nodes


@pytest.fixture
async def test_edges(test_nodes):
    """Create test edges connecting test nodes."""
    edges = [
        WalkerTestEdge(source=test_nodes[0].id, target=test_nodes[1].id, weight=5),
        WalkerTestEdge(source=test_nodes[1].id, target=test_nodes[2].id, weight=10),
        WalkerTestEdge(source=test_nodes[2].id, target=test_nodes[3].id, weight=15),
    ]
    return edges


class TestWalkerBasicFunctionality:
    """Test basic Walker functionality."""

    async def test_walker_initialization(self):
        """Test Walker initialization."""
        walker = WalkerTestWalker()
        assert walker.id.startswith("w:WalkerTestWalker:")
        assert hasattr(walker.queue, "to_list")  # WalkerQueue object
        assert len(walker.queue) == 0
        assert await walker.get_report() == []
        assert walker.current_node is None
        assert not walker.paused

    async def test_walker_custom_id(self):
        """Test Walker with custom ID."""
        custom_id = "custom_walker_id"
        walker = WalkerTestWalker(id=custom_id)
        assert walker.id == custom_id

    async def test_walker_report_initialization(self):
        """Test Walker report initialization."""
        walker = WalkerTestWalker()
        assert await walker.get_report() == []

    async def test_here_property(self):
        """Test the 'here' property returns current_node."""
        walker = WalkerTestWalker()
        node = WalkerTestNode(name="test")

        assert walker.here is None
        walker.current_node = node
        assert walker.here == node

    async def test_visitor_property(self):
        """Test the 'visitor' property returns the walker itself."""
        walker = WalkerTestWalker()
        assert walker.visitor == walker


class TestWalkerQueueOperations:
    """Test Walker queue manipulation methods."""

    async def test_visit_single_node(self):
        """Test adding a single node to queue via visit()."""
        walker = WalkerTestWalker()
        node = WalkerTestNode(name="test")

        result = await walker.visit(node)
        assert len(result) == 1
        assert result[0] == node
        assert len(walker.queue) == 1
        queue_list = walker.queue.to_list()
        assert queue_list[0] == node

    async def test_visit_multiple_nodes(self):
        """Test adding multiple nodes to queue via visit()."""
        walker = WalkerTestWalker()
        nodes = [WalkerTestNode(name=f"node{i}") for i in range(3)]

        result = await walker.visit(nodes)
        assert len(result) == 3
        assert result == nodes
        assert len(walker.queue) == 3
        assert await walker.get_queue() == nodes

    async def test_append_nodes(self):
        """Test append() method for adding nodes to queue end."""
        walker = WalkerTestWalker()
        nodes = [WalkerTestNode(name=f"node{i}") for i in range(3)]

        result = await walker.append(nodes[0])
        assert result == [nodes[0]]
        assert len(walker.queue) == 1

        result = await walker.append(nodes[1:])
        assert result == nodes[1:]
        assert len(walker.queue) == 3
        assert await walker.get_queue() == nodes

    async def test_prepend_nodes(self):
        """Test prepend() method for adding nodes to queue beginning."""
        walker = WalkerTestWalker()
        nodes = [WalkerTestNode(name=f"node{i}") for i in range(3)]

        # Add initial node
        await walker.append(nodes[0])

        # Prepend should add to beginning
        result = await walker.prepend(nodes[1:])
        assert result == nodes[1:]
        assert len(walker.queue) == 3
        # Should maintain relative order: node1, node2, node0
        assert await walker.get_queue() == [nodes[1], nodes[2], nodes[0]]

    async def test_add_next_nodes(self):
        """Test add_next() method for adding nodes next in queue."""
        walker = WalkerTestWalker()
        nodes = [WalkerTestNode(name=f"node{i}") for i in range(4)]

        # Add initial nodes
        await walker.append(nodes[:2])

        # Add next should insert at beginning of queue
        result = await walker.add_next(nodes[2:])
        assert result == nodes[2:]
        assert len(walker.queue) == 4
        # Should be: node2, node3, node0, node1
        assert await walker.get_queue() == [nodes[2], nodes[3], nodes[0], nodes[1]]

    async def test_dequeue_nodes(self):
        """Test dequeue() method for removing nodes from queue."""
        walker = WalkerTestWalker()
        nodes = [WalkerTestNode(name=f"node{i}") for i in range(4)]

        # Add all nodes
        await walker.append(nodes)
        assert len(walker.queue) == 4

        # Remove single node
        result = await walker.dequeue(nodes[1])
        assert result == [nodes[1]]
        assert len(walker.queue) == 3
        assert nodes[1] not in walker.queue

        # Remove multiple nodes
        result = await walker.dequeue([nodes[0], nodes[2]])
        assert len(result) == 2
        assert nodes[0] in result
        assert nodes[2] in result
        assert len(walker.queue) == 1
        assert await walker.get_queue() == [nodes[3]]

    async def test_insert_after_node(self):
        """Test insert_after() method."""
        walker = WalkerTestWalker()
        nodes = [WalkerTestNode(name=f"node{i}") for i in range(5)]

        # Add initial nodes: 0, 1, 2
        await walker.append(nodes[:3])

        # Insert after node1
        result = await walker.insert_after(nodes[1], nodes[3:])
        assert result == nodes[3:]
        assert len(walker.queue) == 5
        # Should be: node0, node1, node3, node4, node2
        expected_order = [nodes[0], nodes[1], nodes[3], nodes[4], nodes[2]]
        assert walker.queue.to_list() == expected_order

    async def test_insert_after_nonexistent_node(self):
        """Test insert_after() with node not in queue."""
        walker = WalkerTestWalker()
        nodes = [WalkerTestNode(name=f"node{i}") for i in range(3)]

        await walker.append(nodes[:2])

        with pytest.raises(ValueError, match="Target node .* not found in queue"):
            await walker.insert_after(nodes[2], [WalkerTestNode(name="new")])

    async def test_insert_before_node(self):
        """Test insert_before() method."""
        walker = WalkerTestWalker()
        nodes = [WalkerTestNode(name=f"node{i}") for i in range(5)]

        # Add initial nodes: 0, 1, 2
        await walker.append(nodes[:3])

        # Insert before node1
        result = await walker.insert_before(nodes[1], nodes[3:])
        assert result == nodes[3:]
        assert len(walker.queue) == 5
        # Should be: node0, node3, node4, node1, node2
        expected_order = [nodes[0], nodes[3], nodes[4], nodes[1], nodes[2]]
        assert walker.queue.to_list() == expected_order

    async def test_is_queued(self):
        """Test is_queued() method."""
        walker = WalkerTestWalker()
        nodes = [WalkerTestNode(name=f"node{i}") for i in range(3)]

        # Initially no nodes queued
        assert not await walker.is_queued(nodes[0])

        # Add some nodes
        await walker.append(nodes[:2])
        assert await walker.is_queued(nodes[0])
        assert await walker.is_queued(nodes[1])
        assert not await walker.is_queued(nodes[2])

    async def test_get_queue(self):
        """Test get_queue() method."""
        walker = WalkerTestWalker()
        nodes = [WalkerTestNode(name=f"node{i}") for i in range(3)]

        # Empty queue
        queue_list = await walker.get_queue()
        assert queue_list == []

        # Add nodes and verify
        await walker.append(nodes)
        queue_list = await walker.get_queue()
        assert queue_list == nodes
        assert isinstance(queue_list, list)  # Should return list, not deque

    async def test_clear_queue(self):
        """Test clear_queue() method."""
        walker = WalkerTestWalker()
        nodes = [WalkerTestNode(name=f"node{i}") for i in range(3)]

        await walker.append(nodes)
        assert len(walker.queue) == 3

        await walker.clear_queue()
        assert len(walker.queue) == 0


class TestWalkerTraversalBasic:
    """Test basic Walker traversal functionality."""

    @pytest.mark.asyncio
    async def test_spawn_with_root_node(self):
        """Test spawn() method with root node."""
        root_node = WalkerTestNode(name="root", id="n:Root:root")
        walker = WalkerTestWalker()
        result = await walker.spawn(root_node)

        assert result == walker
        assert "root" in walker.visited_nodes
        assert walker.exit_called

    @pytest.mark.asyncio
    async def test_spawn_with_custom_start_node(self):
        """Test spawn() method with custom start node."""
        start_node = WalkerTestNode(name="start")
        walker = WalkerTestWalker()

        result = await walker.spawn(start_node)

        assert result == walker
        assert "start" in walker.visited_nodes
        assert walker.exit_called

    @pytest.mark.asyncio
    async def test_multiple_node_traversal(self):
        """Test traversal through multiple nodes."""
        nodes = [WalkerTestNode(name=f"node{i}") for i in range(3)]
        walker = WalkerTestWalker()

        # Queue multiple nodes
        await walker.visit(nodes)

        # Start traversal from first node
        result = await walker.spawn(nodes[0])

        assert result == walker
        # Should visit all nodes
        assert len(walker.visited_nodes) >= len(nodes)
        assert all(node.name in walker.visited_nodes for node in nodes)

    @pytest.mark.asyncio
    async def test_visiting_context_manager(self):
        """Test visiting() context manager functionality."""
        walker = WalkerTestWalker()
        node = WalkerTestNode(name="test")

        assert walker.current_node is None
        assert node.visitor is None

        with await walker.visiting(node):
            assert walker.current_node == node
            assert node.visitor == walker

        # After context exits
        assert walker.current_node is None
        assert node.visitor is None

    @pytest.mark.asyncio
    async def test_hook_execution_order(self):
        """Test that visit and exit hooks execute in correct order."""
        walker = ControlFlowWalker()
        nodes = [WalkerTestNode(name=f"node{i}") for i in range(2)]

        await walker.visit(nodes)
        await walker.spawn(nodes[0])

        # Should have visit events for all nodes plus exit
        expected_events = ["visited:node0", "visited:node1", "exit:called"]
        assert walker.events == expected_events


class TestWalkerControlFlow:
    """Test Walker control flow methods."""

    @pytest.mark.asyncio
    async def test_skip_functionality(self):
        """Test skip() method halts current node processing."""
        walker = SkippingWalker()
        nodes = [
            WalkerTestNode(name="normal"),
            WalkerTestNode(name="skip_this"),
            WalkerTestNode(name="also_normal"),
        ]

        await walker.visit(nodes)
        await walker.spawn(nodes[0])

        # Should visit normal nodes but skip the skip_this node
        assert "normal" in walker.visited_nodes
        assert "also_normal" in walker.visited_nodes
        assert "skip_this" in walker.skipped_nodes
        assert "SHOULD_NOT_REACH" not in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_pause_functionality(self):
        """Test pause() method pauses traversal."""
        walker = PausingWalker()
        walker.pause_after = "node1"

        nodes = [
            WalkerTestNode(name="node0"),
            WalkerTestNode(name="node1"),
            WalkerTestNode(name="node2"),
        ]

        await walker.visit(nodes)
        await walker.spawn(nodes[0])

        # Should be paused and have visited up to pause point
        assert walker.paused
        assert "node0" in walker.visited_nodes
        assert "node1" in walker.visited_nodes
        assert "node2" not in walker.visited_nodes
        assert len(walker.queue) > 0  # Should have remaining nodes

    @pytest.mark.asyncio
    async def test_resume_functionality(self):
        """Test resume() method continues paused traversal."""
        walker = PausingWalker()
        walker.pause_after = "node1"

        nodes = [
            WalkerTestNode(name="node0"),
            WalkerTestNode(name="node1"),
            WalkerTestNode(name="node2"),
        ]

        await walker.visit(nodes)
        await walker.spawn(nodes[0])

        # Verify paused state
        assert walker.paused
        assert len(walker.queue) > 0

        # Resume traversal
        result = await walker.resume()

        assert result == walker
        assert not walker.paused
        assert "node2" in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_disengage_functionality(self):
        """Test disengage() method halts walker."""
        walker = WalkerTestWalker()
        node = WalkerTestNode(name="test")
        walker.current_node = node
        node.set_visitor(walker)

        result = await walker.disengage()

        assert result == walker
        assert walker.paused
        assert walker.current_node is None
        assert node.visitor is None

    @pytest.mark.asyncio
    async def test_resume_unpaused_walker(self):
        """Test resume() on unpaused walker returns immediately."""
        walker = WalkerTestWalker()
        assert not walker.paused

        result = await walker.resume()
        assert result == walker
        assert not walker.paused


class TestWalkerDecorators:
    """Test @on_visit and @on_exit decorators."""

    async def test_on_visit_decorator_registration(self):
        """Test @on_visit decorator registers hooks correctly."""
        # Check that hooks are registered in class
        assert WalkerTestNode in WalkerTestWalker._visit_hooks
        assert WalkerTestEdge in WalkerTestWalker._visit_hooks

        # Check hook methods are stored
        node_hooks = WalkerTestWalker._visit_hooks[WalkerTestNode]
        edge_hooks = WalkerTestWalker._visit_hooks[WalkerTestEdge]

        assert len(node_hooks) >= 1
        assert len(edge_hooks) >= 1
        assert any("visit_test_node" in str(hook) for hook in node_hooks)
        assert any("visit_test_edge" in str(hook) for hook in edge_hooks)

    async def test_on_exit_decorator_registration(self):
        """Test @on_exit decorator marks methods correctly."""
        walker = WalkerTestWalker()
        exit_method = walker.on_walker_exit
        assert hasattr(exit_method, "_on_exit")
        assert getattr(exit_method, "_on_exit") is True

    @pytest.mark.asyncio
    async def test_visit_hook_execution(self):
        """Test visit hooks execute when visiting nodes."""
        walker = WalkerTestWalker()
        node = WalkerTestNode(name="test")

        # Simulate hook execution
        await walker.visit_test_node(node)
        assert "test" in walker.visited_nodes

    @pytest.mark.asyncio
    async def test_multiple_hooks_same_type(self):
        """Test multiple hooks for same node type."""

        class MultiHookWalker(Walker):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.hook1_calls = []
                self.hook2_calls = []

            @on_visit(WalkerTestNode)
            async def hook1(self, here):
                self.hook1_calls.append(here.name)

            @on_visit(WalkerTestNode)
            async def hook2(self, here):
                self.hook2_calls.append(here.name)

        walker = MultiHookWalker()
        node = WalkerTestNode(name="test")

        await walker.spawn(node)

        # Both hooks should execute
        assert "test" in walker.hook1_calls
        assert "test" in walker.hook2_calls


class TestWalkerErrorHandling:
    """Test Walker error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_hook_execution_error(self):
        """Test error handling during hook execution."""

        class ErrorWalker(Walker):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.hook_errors = []

            @on_visit(WalkerTestNode)
            async def error_hook(self, here):
                if here.name == "error_node":
                    raise ValueError("Test error in hook")
                # Normal processing
                pass

        walker = ErrorWalker()
        nodes = [
            WalkerTestNode(name="normal"),
            WalkerTestNode(name="error_node"),
            WalkerTestNode(name="after_error"),
        ]

        await walker.visit(nodes)
        await walker.spawn(nodes[0])

        # Walker should continue despite hook errors
        # Check that error was logged to report
        report = await walker.get_report()
        assert any("hook_error" in item for item in report if isinstance(item, dict))

    @pytest.mark.asyncio
    async def test_traversal_exception_handling(self):
        """Test overall traversal exception handling."""

        class FailingWalker(Walker):
            @on_visit(WalkerTestNode)
            async def failing_hook(self, here):
                if here.name == "crash":
                    raise RuntimeError("Simulated crash")

        walker = FailingWalker()
        nodes = [WalkerTestNode(name="crash")]

        await walker.visit(nodes)
        # Should not raise exception, but handle gracefully
        result = await walker.spawn(nodes[0])

        assert result == walker
        report = await walker.get_report()
        assert any("hook_error" in item for item in report if isinstance(item, dict))

    @pytest.mark.asyncio
    async def test_skip_outside_traversal(self):
        """Test skip() raises exception when not in traversal."""
        walker = WalkerTestWalker()

        with pytest.raises(JVSpatialError):
            await walker.skip()

    @pytest.mark.asyncio
    async def test_pause_outside_traversal(self):
        """Test pause() raises exception when not in traversal."""
        walker = WalkerTestWalker()

        with pytest.raises(WalkerError):
            await walker.pause("Test pause")


class TestWalkerEdgeCases:
    """Test Walker edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_queue_traversal(self):
        """Test traversal with empty queue."""
        walker = WalkerTestWalker()

        # Spawn with no queued items (except start node)
        start_node = WalkerTestNode(name="start")
        result = await walker.spawn(start_node)

        assert result == walker
        assert "start" in walker.visited_nodes
        assert walker.exit_called

    @pytest.mark.asyncio
    async def test_queue_modification_during_traversal(self):
        """Test modifying queue during traversal."""

        class ModifyingWalker(Walker):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.visited = []

            @on_visit(WalkerTestNode)
            async def modify_queue(self, here):
                self.visited.append(here.name)
                if here.name == "node0":
                    # Add more nodes during traversal
                    new_node = WalkerTestNode(name="added_during_traversal")
                    await self.visit(new_node)

        walker = ModifyingWalker()
        nodes = [WalkerTestNode(name="node0"), WalkerTestNode(name="node1")]

        await walker.visit(nodes)
        await walker.spawn(nodes[0])

        # Should visit dynamically added node
        assert "added_during_traversal" in walker.visited

    @pytest.mark.asyncio
    async def test_walker_reuse(self):
        """Test reusing walker for multiple traversals."""
        walker = WalkerTestWalker()

        # First traversal
        node1 = WalkerTestNode(name="first")
        await walker.spawn(node1)
        first_visits = walker.visited_nodes.copy()

        # Reset for second traversal
        walker.visited_nodes.clear()
        walker.exit_called = False
        walker._report.clear()

        # Second traversal
        node2 = WalkerTestNode(name="second")
        await walker.spawn(node2)

        assert "second" in walker.visited_nodes
        assert walker.exit_called
        # Should not have first traversal data
        assert "first" not in walker.visited_nodes
