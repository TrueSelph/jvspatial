"""
Test suite for Walker trail tracking functionality.

Tests the new always-on trail tracking system with TrailTracker component.
"""

from typing import Any, Dict, List

import pytest

from jvspatial.core.entities import Node, Walker


class TrailTestNode(Node):
    """Test node for trail testing."""

    name: str = "test"
    value: int = 10
    category: str = ""


class TrailTrackingWalker(Walker):
    """Test walker for trail testing."""

    pass


class TestWalkerTrailInitialization:
    """Test Walker trail initialization in new architecture."""

    async def test_trail_always_enabled(self):
        """Test that trail tracking is always enabled in new architecture."""
        walker = TrailTrackingWalker()

        # Trail tracking is always enabled in new architecture
        assert hasattr(walker, "_trail_tracker")
        assert walker._trail_tracker is not None

    async def test_trail_tracker_initialization(self):
        """Test that TrailTracker is properly initialized."""
        walker = TrailTrackingWalker()

        # Check that trail tracker is initialized
        assert hasattr(walker, "_trail_tracker")
        assert walker._trail_tracker.get_trail() == []
        assert walker._trail_tracker.get_length() == 0

    async def test_trail_data_structure(self):
        """Test the new trail data structure."""
        walker = TrailTrackingWalker()
        node = TrailTestNode(name="test_node")

        # Record a trail step using visiting context
        with await walker.visiting(node):
            pass

        trail = walker.get_trail()
        assert len(trail) == 1
        assert isinstance(trail[0], str)  # Trail contains node ID strings
        assert trail[0] == node.id

        # Check trail data in TrailTracker
        trail_data = walker._trail_tracker.get_trail()
        assert len(trail_data) == 1
        assert isinstance(trail_data[0], dict)
        assert trail_data[0]["node"] == node.id


class TestTrailRecording:
    """Test trail recording functionality."""

    async def test_visiting_context_manager(self):
        """Test that visiting context manager records trail steps."""
        walker = TrailTrackingWalker()
        node = TrailTestNode(name="test_node")

        # Use visiting context manager
        with await walker.visiting(node):
            pass

        trail = walker.get_trail()
        assert len(trail) == 1
        assert trail[0] == node.id

        # Check trail data structure
        trail_data = walker._trail_tracker.get_trail()
        assert len(trail_data) == 1
        assert trail_data[0]["node"] == node.id
        assert trail_data[0]["node_type"] == "TrailTestNode"

    async def test_visiting_context_manager_with_edge(self):
        """Test visiting context manager with edge tracking."""
        walker = TrailTrackingWalker()
        node = TrailTestNode(name="test_node")
        edge_id = "e:Edge:test123"

        # Use visiting context manager with edge
        with await walker.visiting(node, edge_from_previous=edge_id):
            pass

        trail = walker.get_trail()
        assert len(trail) == 1
        assert trail[0] == node.id

        # Check trail data structure
        trail_data = walker._trail_tracker.get_trail()
        assert len(trail_data) == 1
        assert trail_data[0]["node"] == node.id
        assert trail_data[0]["edge"] == edge_id

    async def test_multiple_trail_steps(self):
        """Test recording multiple trail steps."""
        walker = TrailTrackingWalker()
        nodes = [TrailTestNode(name=f"node{i}") for i in range(3)]

        # Record multiple steps
        for node in nodes:
            with await walker.visiting(node):
                pass

        trail = walker.get_trail()
        assert len(trail) == 3
        for i, node in enumerate(nodes):
            assert trail[i] == node.id

    async def test_trail_step_metadata(self):
        """Test that trail steps include metadata."""
        walker = TrailTrackingWalker()
        node = TrailTestNode(name="test_node", value=42)

        with await walker.visiting(node):
            pass

        trail = walker.get_trail()
        assert len(trail) == 1
        assert trail[0] == node.id

        # Check trail data structure for metadata
        trail_data = walker._trail_tracker.get_trail()
        assert len(trail_data) == 1
        step = trail_data[0]
        assert step["node"] == node.id
        assert step["node_type"] == "TrailTestNode"
        assert "timestamp" in step
        assert "queue_length" in step


class TestTrailAccessMethods:
    """Test trail access methods."""

    async def test_get_trail(self):
        """Test get_trail() method."""
        walker = TrailTrackingWalker()
        nodes = [TrailTestNode(name=f"node{i}") for i in range(3)]

        # Record trail steps
        for node in nodes:
            with await walker.visiting(node):
                pass

        trail = walker.get_trail()
        assert len(trail) == 3
        assert all(
            isinstance(step, str) for step in trail
        )  # Trail contains node ID strings

    @pytest.mark.asyncio
    async def test_get_trail_nodes(self):
        """Test get_trail_nodes() method with database persistence."""
        walker = TrailTrackingWalker()
        nodes = [TrailTestNode(name=f"node{i}") for i in range(3)]

        # Persist nodes to database first
        for node in nodes:
            await node.save()

        # Record trail steps
        for node in nodes:
            with await walker.visiting(node):
                pass

        trail_nodes = await walker.get_trail_nodes()
        assert len(trail_nodes) == 3
        assert [node.id for node in trail_nodes] == [node.id for node in nodes]

    @pytest.mark.asyncio
    async def test_get_trail_path(self):
        """Test get_trail_path() method with database persistence."""
        walker = TrailTrackingWalker()
        nodes = [TrailTestNode(name=f"node{i}") for i in range(3)]

        # Persist nodes to database first
        for node in nodes:
            await node.save()

        # Record trail steps
        for node in nodes:
            with await walker.visiting(node):
                pass

        path = walker.get_trail_path()
        assert len(path) == 3
        assert path == [node.id for node in nodes]

    async def test_get_trail_length(self):
        """Test get_trail_length() method."""
        walker = TrailTrackingWalker()
        nodes = [TrailTestNode(name=f"node{i}") for i in range(3)]

        # Record trail steps
        for node in nodes:
            with await walker.visiting(node):
                pass

        assert walker.get_trail_length() == 3

    async def test_get_recent_trail(self):
        """Test get_recent_trail() method."""
        walker = TrailTrackingWalker()
        nodes = [TrailTestNode(name=f"node{i}") for i in range(5)]

        # Record trail steps
        for node in nodes:
            with await walker.visiting(node):
                pass

        # Test getting recent trail
        recent = walker.get_recent_trail(3)
        assert len(recent) == 3
        assert recent == [node.id for node in nodes[-3:]]

    async def test_has_visited(self):
        """Test has_visited() method."""
        walker = TrailTrackingWalker()
        node1 = TrailTestNode(name="node1")
        node2 = TrailTestNode(name="node2")

        # Visit first node
        with await walker.visiting(node1):
            pass

        assert walker.has_visited(node1.id) is True
        assert walker.has_visited(node2.id) is False

    async def test_get_visit_count(self):
        """Test get_visit_count() method."""
        walker = TrailTrackingWalker()
        node = TrailTestNode(name="test_node")

        # Visit node multiple times
        for _ in range(3):
            with await walker.visiting(node):
                pass

        assert await walker.get_visit_count(node.id) == 3

    async def test_detect_cycles(self):
        """Test detect_cycles() method."""
        walker = TrailTrackingWalker()
        nodes = [TrailTestNode(name=f"node{i}") for i in range(3)]

        # Create a cycle: node0 -> node1 -> node2 -> node0
        for node in nodes:
            with await walker.visiting(node):
                pass
        with await walker.visiting(nodes[0]):  # Back to first node
            pass

        cycles = await walker.detect_cycles()
        assert len(cycles) > 0  # Should detect the cycle

    async def test_get_trail_summary(self):
        """Test get_trail_summary() method."""
        walker = TrailTrackingWalker()
        nodes = [TrailTestNode(name=f"node{i}") for i in range(3)]

        # Record trail steps
        for node in nodes:
            with await walker.visiting(node):
                pass

        summary = walker.get_trail_summary()
        assert "length" in summary
        assert "unique_nodes" in summary
        assert "cycles_detected" in summary
        assert "cycle_ranges" in summary
        assert "most_visited" in summary
        assert "recent_nodes" in summary
        assert summary["length"] == 3
        assert summary["unique_nodes"] == 3


class TestTrailManagementMethods:
    """Test trail management methods."""

    async def test_clear_trail(self):
        """Test clear_trail() method."""
        walker = TrailTrackingWalker()
        nodes = [TrailTestNode(name=f"node{i}") for i in range(3)]

        # Record trail steps
        for node in nodes:
            with await walker.visiting(node):
                pass

        assert walker.get_trail_length() == 3

        # Clear trail
        walker.clear_trail()
        assert walker.get_trail_length() == 0
        assert walker.get_trail() == []


class TestTrailIntegrationWithTraversal:
    """Test trail integration with Walker traversal."""

    @pytest.mark.asyncio
    async def test_trail_during_spawn(self):
        """Test that trail is recorded during spawn."""
        walker = TrailTrackingWalker()
        nodes = [TrailTestNode(name=f"node{i}") for i in range(3)]

        # Add nodes to queue
        await walker.visit(nodes)

        # Spawn should record trail steps
        await walker.spawn(nodes[0])

        # Check that trail was recorded
        trail = walker.get_trail()
        assert len(trail) > 0

    @pytest.mark.asyncio
    async def test_trail_during_resume(self):
        """Test that trail is recorded during resume."""
        walker = TrailTrackingWalker()
        nodes = [TrailTestNode(name=f"node{i}") for i in range(3)]

        # Add nodes to queue
        await walker.visit(nodes)

        # Start the walker first
        await walker.spawn(nodes[0])

        # Pause the walker
        walker.paused = True

        # Resume should record trail steps
        await walker.resume()

        # Check that trail was recorded
        trail = walker.get_trail()
        assert len(trail) > 0

    @pytest.mark.asyncio
    async def test_trail_with_protection(self):
        """Test trail recording with protection limits."""
        walker = TrailTrackingWalker(max_steps=2)
        nodes = [TrailTestNode(name=f"node{i}") for i in range(5)]

        # Add nodes to queue
        await walker.visit(nodes)

        # Spawn with protection should record trail steps
        await walker.spawn(nodes[0])

        # Check that trail was recorded
        trail = walker.get_trail()
        assert len(trail) > 0
        assert len(trail) <= 2  # Should be limited by max_steps


class TestTrailEdgeCases:
    """Test trail edge cases."""

    async def test_empty_trail(self):
        """Test operations on empty trail."""
        walker = TrailTrackingWalker()

        assert walker.get_trail() == []
        assert walker.get_trail_length() == 0
        assert walker.get_recent_trail(5) == []
        assert await walker.detect_cycles() == []

    async def test_trail_with_duplicate_nodes(self):
        """Test trail with duplicate node visits."""
        walker = TrailTrackingWalker()
        node = TrailTestNode(name="duplicate_node")

        # Visit same node multiple times
        for _ in range(3):
            with await walker.visiting(node):
                pass

        trail = walker.get_trail()
        assert len(trail) == 3
        assert await walker.get_visit_count(node.id) == 3

    @pytest.mark.asyncio
    async def test_trail_with_missing_nodes(self):
        """Test trail with nodes that no longer exist."""
        walker = TrailTrackingWalker()
        node = TrailTestNode(name="test_node")

        # Persist node to database first
        await node.save()

        # Record trail step
        with await walker.visiting(node):
            pass

        # Get trail nodes (should handle missing nodes gracefully)
        trail_nodes = await walker.get_trail_nodes()
        assert len(trail_nodes) == 1
        assert trail_nodes[0].id == node.id

    async def test_trail_summary_empty(self):
        """Test trail summary with empty trail."""
        walker = TrailTrackingWalker()

        summary = walker.get_trail_summary()
        assert summary["length"] == 0
        assert summary["unique_nodes"] == 0
        assert summary["cycles_detected"] == 0
        assert summary["cycle_ranges"] == []
        assert summary["most_visited"] is None
        assert summary["recent_nodes"] == []

    async def test_trail_summary_with_cycles(self):
        """Test trail summary with cycles."""
        walker = TrailTrackingWalker()
        nodes = [TrailTestNode(name=f"node{i}") for i in range(3)]

        # Create a cycle
        for node in nodes:
            with await walker.visiting(node):
                pass
        with await walker.visiting(nodes[0]):  # Back to first node
            pass

        summary = walker.get_trail_summary()
        assert summary["length"] == 4
        assert summary["unique_nodes"] == 3
        assert summary["cycles_detected"] > 0
        assert len(summary["cycle_ranges"]) > 0
