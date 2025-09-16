"""
Unit tests for Walker skip() functionality.

Tests the skip() method that allows walkers to immediately halt processing
of the current node and proceed to the next node in the queue, similar to
'continue' in typical loops.
"""

from typing import List
from unittest.mock import AsyncMock

import pytest

from jvspatial.core.entities import (
    Node,
    Root,
    TraversalSkipped,
    Walker,
    on_exit,
    on_visit,
)


class TestNode(Node):
    """Test node with various properties for skip testing."""

    name: str
    should_skip: bool = False
    priority: str = "normal"
    visited: bool = False
    status: str = "active"


class BasicSkipWalker(Walker):
    """Walker that demonstrates basic skip() functionality."""

    @on_visit(Root)
    async def start_traversal(self, here):
        """Create test nodes and start traversal."""
        if "events" not in self.response:
            self.response["events"] = []

        self.response["events"].append("start_traversal")

        # Create test nodes - some should be skipped
        node_a = await TestNode.create(name="A", should_skip=False)
        node_b = await TestNode.create(name="B", should_skip=True)  # Skip this
        node_c = await TestNode.create(name="C", should_skip=False)
        node_d = await TestNode.create(name="D", should_skip=True)  # Skip this
        node_e = await TestNode.create(name="E", should_skip=False)

        await self.visit([node_a, node_b, node_c, node_d, node_e])

        self.response["events"].append("queued_all_nodes")

    @on_visit(TestNode)
    async def process_node(self, here):
        """Process each test node, skipping when required."""
        if "events" not in self.response:
            self.response["events"] = []

        self.response["events"].append(f"visiting_{here.name}")

        # Skip nodes that are marked for skipping
        if here.should_skip:
            self.response["events"].append(f"skipping_{here.name}")
            self.skip()  # This should halt execution and move to next node

            # This code should NEVER be reached for skipped nodes
            self.response["events"].append(f"ERROR_after_skip_{here.name}")
            return

        # Normal processing for non-skipped nodes
        self.response["events"].append(f"processing_{here.name}")
        here.visited = True
        await here.save()
        self.response["events"].append(f"processed_{here.name}")

    @on_exit
    async def finalize(self):
        """Finalize traversal."""
        if "events" not in self.response:
            self.response["events"] = []
        self.response["events"].append("traversal_complete")


class ConditionalSkipWalker(Walker):
    """Walker that skips based on dynamic conditions."""

    @on_visit(Root)
    async def setup(self, here):
        """Setup test with different node types."""
        if "results" not in self.response:
            self.response["results"] = []

        # Create nodes with different conditions
        normal = await TestNode.create(name="NORMAL")
        skip_node = await TestNode.create(name="SKIP_NODE")
        process_node = await TestNode.create(name="PROCESS_NODE")

        await self.visit([normal, skip_node, process_node])

    @on_visit(TestNode)
    async def handle_node(self, here):
        """Handle nodes with conditional skipping."""
        if "results" not in self.response:
            self.response["results"] = []

        self.response["results"].append(f"handling_{here.name}")

        # Skip nodes with "SKIP" in their name
        if "SKIP" in here.name:
            self.response["results"].append(f"condition_met_skip_{here.name}")
            self.skip()
            # Should not reach here
            self.response["results"].append(f"ERROR_post_skip_{here.name}")

        # Process other nodes normally
        self.response["results"].append(f"completed_{here.name}")


class QueueManipulationSkipWalker(Walker):
    """Walker that combines skip() with queue operations."""

    @on_visit(Root)
    async def start(self, here):
        """Start with initial nodes."""
        if "flow" not in self.response:
            self.response["flow"] = []

        node1 = await TestNode.create(name="FIRST")
        node2 = await TestNode.create(name="SECOND")

        await self.visit([node1, node2])

    @on_visit(TestNode)
    async def process_with_queue_ops(self, here):
        """Process nodes while manipulating queue."""
        if "flow" not in self.response:
            self.response["flow"] = []

        self.response["flow"].append(f"processing_{here.name}")

        # Add dynamic node when processing FIRST
        if here.name == "FIRST":
            dynamic = await TestNode.create(name="DYNAMIC")
            self.add_next(dynamic)  # Add to front of queue
            self.response["flow"].append("added_dynamic_next")

        # Skip SECOND node
        elif here.name == "SECOND":
            self.response["flow"].append("skipping_second")
            self.skip()
            self.response["flow"].append("ERROR_after_second_skip")

        # Process normally
        self.response["flow"].append(f"finished_{here.name}")


class ErrorConditionSkipWalker(Walker):
    """Walker for testing skip() in error conditions."""

    @on_visit(Root)
    async def setup(self, here):
        if "log" not in self.response:
            self.response["log"] = []

        error_node = await TestNode.create(name="ERROR_TEST")
        await self.visit([error_node])

    @on_visit(TestNode)
    async def error_then_skip(self, here):
        if "log" not in self.response:
            self.response["log"] = []

        self.response["log"].append(f"before_skip_{here.name}")

        # Test that skip() works even in error conditions
        try:
            # Simulate some error condition that leads to skip
            if here.name == "ERROR_TEST":
                self.response["log"].append("error_detected")
                self.skip()
                # This should not execute
                self.response["log"].append("ERROR_post_skip")
        except Exception as e:
            # Skip should not cause exceptions to propagate unexpectedly
            self.response["log"].append(f"UNEXPECTED_EXCEPTION_{str(e)}")


class PrioritySkipWalker(Walker):
    """Walker that skips based on priority levels."""

    def __init__(self, min_priority="medium", **kwargs):
        super().__init__(**kwargs)
        # Store in response dict to avoid Pydantic field issues
        self.response["_priority_levels"] = {
            "low": 1,
            "medium": 2,
            "high": 3,
            "critical": 4,
        }
        self.response["_min_priority_level"] = self.response["_priority_levels"][
            min_priority
        ]

    @on_visit(Root)
    async def setup_priority_test(self, here):
        if "processed" not in self.response:
            self.response["processed"] = []
            self.response["skipped"] = []

        # Create nodes with different priorities
        low_node = await TestNode.create(name="LOW_PRIORITY", priority="low")
        medium_node = await TestNode.create(name="MEDIUM_PRIORITY", priority="medium")
        high_node = await TestNode.create(name="HIGH_PRIORITY", priority="high")
        critical_node = await TestNode.create(
            name="CRITICAL_PRIORITY", priority="critical"
        )

        await self.visit([low_node, medium_node, high_node, critical_node])

    @on_visit(TestNode)
    async def filter_by_priority(self, here):
        if "processed" not in self.response:
            self.response["processed"] = []
            self.response["skipped"] = []

        priority_levels = self.response.get("_priority_levels", {})
        min_priority_level = self.response.get("_min_priority_level", 1)
        node_priority_level = priority_levels.get(here.priority, 0)

        if node_priority_level < min_priority_level:
            self.response["skipped"].append(here.name)
            self.skip()
            # Should not execute
            self.response["processed"].append(f"ERROR_processed_{here.name}")

        self.response["processed"].append(here.name)


@pytest.mark.asyncio
class TestWalkerSkipFunctionality:
    """Test suite for Walker skip() functionality."""

    async def test_basic_skip_functionality(self):
        """Test basic skip() functionality."""
        walker = BasicSkipWalker()
        result = await walker.spawn()

        events = result.response.get("events", [])

        # Verify correct nodes were processed
        processed_nodes = [
            e.split("_")[1] for e in events if e.startswith("processed_")
        ]
        skipped_nodes = [e.split("_")[1] for e in events if e.startswith("skipping_")]

        # Assertions
        assert processed_nodes == [
            "A",
            "C",
            "E",
        ], f"Expected [A, C, E], got {processed_nodes}"
        assert skipped_nodes == ["B", "D"], f"Expected [B, D], got {skipped_nodes}"

        # Ensure no ERROR events (code after skip() should not execute)
        error_events = [e for e in events if "ERROR_" in e]
        assert not error_events, f"Found error events: {error_events}"

        # Verify traversal completed
        assert "traversal_complete" in events

    async def test_conditional_skip(self):
        """Test conditional skip scenarios."""
        walker = ConditionalSkipWalker()
        result = await walker.spawn()

        results = result.response.get("results", [])

        # Verify conditional skipping worked
        assert "condition_met_skip_SKIP_NODE" in results
        assert "ERROR_post_skip_SKIP_NODE" not in results
        assert "completed_NORMAL" in results
        assert "completed_PROCESS_NODE" in results

    async def test_skip_with_queue_operations(self):
        """Test skip() combined with queue operations."""
        walker = QueueManipulationSkipWalker()
        result = await walker.spawn()

        flow = result.response.get("flow", [])

        # Verify execution flow
        assert "processing_FIRST" in flow
        assert "finished_FIRST" in flow
        assert "added_dynamic_next" in flow

        assert "processing_DYNAMIC" in flow  # Dynamic node should be processed
        assert "finished_DYNAMIC" in flow

        assert "processing_SECOND" in flow
        assert "skipping_second" in flow
        assert "ERROR_after_second_skip" not in flow  # Should not execute after skip
        assert "finished_SECOND" not in flow  # Should not execute after skip

    async def test_skip_error_conditions(self):
        """Test skip() behavior in edge cases."""
        walker = ErrorConditionSkipWalker()
        result = await walker.spawn()

        log = result.response.get("log", [])

        assert "before_skip_ERROR_TEST" in log
        assert "error_detected" in log
        assert "ERROR_post_skip" not in log
        # Note: The "Error executing hook" message in console is expected
        # because TraversalSkipped is raised as part of normal skip() operation

    async def test_priority_filtering_skip(self):
        """Test skip() with priority-based filtering."""
        # Test with medium priority threshold
        walker = PrioritySkipWalker(min_priority="medium")
        result = await walker.spawn()

        processed = result.response.get("processed", [])
        skipped = result.response.get("skipped", [])

        # Should process medium, high, critical
        expected_processed = ["MEDIUM_PRIORITY", "HIGH_PRIORITY", "CRITICAL_PRIORITY"]
        assert (
            processed == expected_processed
        ), f"Expected {expected_processed}, got {processed}"

        # Should skip low
        assert "LOW_PRIORITY" in skipped

        # Ensure no errors (no nodes processed after skip)
        error_processed = [p for p in processed if p.startswith("ERROR_")]
        assert not error_processed

    async def test_skip_exception_type(self):
        """Test that skip() raises the correct exception type."""
        walker = Walker()

        # skip() should raise TraversalSkipped exception
        with pytest.raises(TraversalSkipped):
            walker.skip()

    async def test_skip_with_empty_queue(self):
        """Test skip() behavior with empty queue."""

        class EmptyQueueWalker(Walker):
            @on_visit(Root)
            async def process_root_only(self, here):
                if "events" not in self.response:
                    self.response["events"] = []
                self.response["events"].append("processing_root")
                # No nodes added to queue, so this should be the only processing

        walker = EmptyQueueWalker()
        result = await walker.spawn()

        events = result.response.get("events", [])
        assert "processing_root" in events
        # Should complete normally even with no nodes in queue

    async def test_skip_preserves_walker_state(self):
        """Test that skip() doesn't corrupt walker state."""

        class StateTrackingWalker(Walker):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                # Store state in response to avoid Pydantic issues

            @on_visit(Root)
            async def track_state(self, here):
                self.response["initial_queue_size"] = len(self.queue)

                node1 = await TestNode.create(name="TRACK1", should_skip=True)
                node2 = await TestNode.create(name="TRACK2", should_skip=False)

                await self.visit([node1, node2])
                self.response["after_visit_queue_size"] = len(self.queue)

            @on_visit(TestNode)
            async def track_processing(self, here):
                if "queue_sizes" not in self.response:
                    self.response["queue_sizes"] = []
                self.response["queue_sizes"].append(len(self.queue))

                if here.should_skip:
                    self.skip()

                # Record that we processed this node
                if "processed" not in self.response:
                    self.response["processed"] = []
                self.response["processed"].append(here.name)

        walker = StateTrackingWalker()
        result = await walker.spawn()

        # Verify state tracking worked
        assert result.response["initial_queue_size"] == 0  # Root only initially
        assert result.response["after_visit_queue_size"] == 2  # After adding 2 nodes

        # Should have processed only the non-skipped node
        processed = result.response.get("processed", [])
        assert "TRACK2" in processed
        assert "TRACK1" not in processed

    async def test_skip_in_try_except_block(self):
        """Test that skip() works correctly within try/except blocks."""

        class TryExceptSkipWalker(Walker):
            @on_visit(Root)
            async def setup_try_except_test(self, here):
                self.response["events"] = []

                node1 = await TestNode.create(name="TRY_SKIP")
                node2 = await TestNode.create(name="EXCEPT_SKIP")
                node3 = await TestNode.create(name="NORMAL")

                await self.visit([node1, node2, node3])

            @on_visit(TestNode)
            async def try_except_skip(self, here):
                self.response["events"].append(f"processing_{here.name}")

                try:
                    if here.name == "TRY_SKIP":
                        self.response["events"].append("in_try_block")
                        self.skip()
                        self.response["events"].append("ERROR_after_skip_in_try")

                    # This should execute for EXCEPT_SKIP and NORMAL
                    self.response["events"].append(f"try_block_end_{here.name}")

                except Exception as e:
                    if here.name == "EXCEPT_SKIP":
                        self.response["events"].append("in_except_block")
                        self.skip()
                        self.response["events"].append("ERROR_after_skip_in_except")
                    else:
                        self.response["events"].append(f"unexpected_exception_{str(e)}")

                self.response["events"].append(f"completed_{here.name}")

        walker = TryExceptSkipWalker()
        result = await walker.spawn()

        events = result.response["events"]

        # Verify try block skip
        assert "in_try_block" in events
        assert "ERROR_after_skip_in_try" not in events
        assert "completed_TRY_SKIP" not in events

        # Verify normal processing continued
        assert "completed_NORMAL" in events

    async def test_multiple_skip_calls(self):
        """Test behavior when skip() might be called multiple times."""

        class MultipleSkipWalker(Walker):
            @on_visit(Root)
            async def setup_multiple_skip(self, here):
                self.response["events"] = []
                node = await TestNode.create(name="MULTI_SKIP")
                await self.visit([node])

            @on_visit(TestNode)
            async def multiple_skip_test(self, here):
                self.response["events"].append("before_first_skip")

                # First skip call
                try:
                    self.skip()
                    self.response["events"].append("ERROR_after_first_skip")
                except TraversalSkipped:
                    # Catch and try to skip again (shouldn't happen in normal usage)
                    self.response["events"].append("caught_first_skip")
                    self.skip()  # This should also work
                    self.response["events"].append("ERROR_after_second_skip")

        walker = MultipleSkipWalker()
        result = await walker.spawn()

        events = result.response["events"]
        assert "before_first_skip" in events
        # The specific behavior here depends on implementation details,
        # but neither error message should appear
        assert "ERROR_after_first_skip" not in events
        assert "ERROR_after_second_skip" not in events
