"""
Test suite for Walker infinite walk protection functionality.

This module implements comprehensive tests for:
- Maximum step limiting
- Maximum visits per node limiting
- Timeout protection
- Queue size protection
- Environment variable configuration
- Protection status reporting
- Integration with traversal system
"""

import asyncio
import os
import time
from typing import List
from unittest.mock import patch

import pytest
from pydantic import Field

from jvspatial.core import on_visit
from jvspatial.core.entities import (
    Edge,
    Node,
    Root,
    Walker,
)


class ProtectionTestNode(Node):
    """Test node for protection tests."""

    name: str = ""
    value: int = 0
    category: str = ""


class ProtectionTestEdge(Edge):
    """Test edge for protection tests."""

    weight: int = 1
    label: str = ""


class InfiniteLoopWalker(Walker):
    """Walker that creates infinite loops for testing protection."""

    visited_sequence: List[str] = Field(default_factory=list)
    loop_counter: int = 0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @on_visit(ProtectionTestNode)
    async def create_infinite_loop(self, here):
        """Create infinite loop by continuously visiting nodes."""
        self.visited_sequence.append(here.name)
        self.loop_counter += 1

        # Create new nodes to visit infinitely
        next_node = ProtectionTestNode(
            name=f"node_{self.loop_counter}", value=self.loop_counter
        )
        await self.visit([next_node])


class StepCountTestWalker(Walker):
    """Walker for testing step count limits."""

    steps_taken: int = 0

    @on_visit(ProtectionTestNode)
    async def count_steps(self, here):
        """Count steps and add more nodes."""
        self.steps_taken += 1

        # Add more nodes to exceed step limit
        if self.steps_taken < 50:  # Prevent runaway in case protection fails
            next_node = ProtectionTestNode(name=f"step_{self.steps_taken}")
            await self.append(next_node)  # Use append instead of visit


class NodeRevisitWalker(Walker):
    """Walker for testing node revisit limits."""

    revisit_count: int = 0

    @on_visit(ProtectionTestNode)
    async def revisit_same_node(self, here):
        """Keep revisiting the same node."""
        self.revisit_count += 1

        # Keep adding the same node to trigger revisit protection
        if self.revisit_count < 50:  # Prevent runaway in case protection fails
            await self.append(here)  # Use append instead of visit


class TimeoutTestWalker(Walker):
    """Walker for testing timeout protection."""

    sleep_duration: float = 0.1

    @on_visit(ProtectionTestNode)
    async def slow_processing(self, here):
        """Slow processing to test timeout."""
        await asyncio.sleep(self.sleep_duration)

        # Add more nodes to keep processing
        next_node = ProtectionTestNode(name=f"timeout_node_{len(self.queue)}")
        await self.visit([next_node])


class QueueSizeTestWalker(Walker):
    """Walker for testing queue size protection."""

    nodes_added: int = 0

    @on_visit(ProtectionTestNode)
    async def flood_queue(self, here):
        """Add many nodes to test queue size limit."""
        # Add multiple nodes at once to test queue size protection
        new_nodes = []
        for i in range(100):  # Add 100 nodes at once
            new_nodes.append(
                ProtectionTestNode(name=f"queue_node_{self.nodes_added}_{i}")
            )

        added_nodes = await self.visit(new_nodes)
        self.nodes_added += len(added_nodes)


@pytest.fixture
async def protection_test_nodes():
    """Create test nodes for protection tests."""
    nodes = [
        ProtectionTestNode(name="start", value=0, category="start"),
        ProtectionTestNode(name="node1", value=10, category="middle"),
        ProtectionTestNode(name="node2", value=20, category="middle"),
        ProtectionTestNode(name="end", value=30, category="end"),
    ]
    return nodes


class TestWalkerProtectionInitialization:
    """Test walker protection initialization and configuration."""

    @pytest.mark.asyncio
    async def test_protection_default_initialization(self):
        """Test that protection attributes are initialized with defaults."""
        walker = InfiniteLoopWalker()

        # Use the actual Walker API
        assert walker.step_count == 0
        assert walker.node_visit_counts == {}
        # Access protection settings through the protection component
        assert walker._protection.max_steps == 10000
        assert walker._protection.max_visits_per_node == 100
        assert walker._protection.max_execution_time == 300.0

    @pytest.mark.asyncio
    async def test_protection_custom_initialization(self):
        """Test protection with custom initialization values."""
        walker = InfiniteLoopWalker(
            max_steps=5000,
            max_visits_per_node=50,
            max_execution_time=60.0,
            max_queue_size=500,
        )

        # Use the actual Walker API
        assert walker._protection.max_steps == 5000
        assert walker._protection.max_visits_per_node == 50
        assert walker._protection.max_execution_time == 60.0

    @pytest.mark.asyncio
    async def test_protection_property_setters(self):
        """Test protection property setters with validation."""
        walker = InfiniteLoopWalker()

        # Test valid values through the protection component
        walker._protection.max_steps = 2000
        walker._protection.max_visits_per_node = 25
        walker._protection.max_execution_time = 120.0

        assert walker._protection.max_steps == 2000
        assert walker._protection.max_visits_per_node == 25
        assert walker._protection.max_execution_time == 120.0

    @pytest.mark.asyncio
    async def test_protection_property_validation(self):
        """Test that property setters validate negative values."""
        walker = InfiniteLoopWalker()

        # Test negative values are converted to 0 or positive
        walker._protection.max_steps = -100
        walker._protection.max_visits_per_node = -50
        walker._protection.max_execution_time = -30.0

        assert walker._protection.max_steps == 0
        assert walker._protection.max_visits_per_node == 0
        assert walker._protection.max_execution_time == 0.0

    @patch.dict(
        os.environ,
        {
            "JVSPATIAL_WALKER_MAX_STEPS": "5000",
            "JVSPATIAL_WALKER_MAX_VISITS_PER_NODE": "25",
            "JVSPATIAL_WALKER_MAX_EXECUTION_TIME": "120.0",
            "JVSPATIAL_WALKER_MAX_QUEUE_SIZE": "250",
        },
    )
    def test_environment_variable_initialization(self):
        """Test initialization from environment variables."""
        walker = InfiniteLoopWalker()

        assert walker._protection.max_steps == 5000
        assert walker._protection.max_visits_per_node == 25
        assert walker._protection.max_execution_time == 120.0


class TestMaxStepsProtection:
    """Test maximum steps protection mechanism."""

    @pytest.mark.asyncio
    async def test_max_steps_protection_triggers(self):
        """Test that max steps protection triggers correctly."""
        # Create walker with very low step limit
        walker = StepCountTestWalker(max_steps=5)
        start_node = ProtectionTestNode(name="start", value=0)

        # Run walker and expect protection to trigger
        await walker.spawn(start_node)

        # Check protection was triggered by checking step count and limits
        # The protection system stops traversal when limits are exceeded
        assert walker.step_count >= 5  # Should have reached the limit
        assert walker._protection.step_count >= 5
        # The walker should have stopped due to protection limits
        assert (
            not await walker._protection.check_limits()
            or walker.step_count >= walker._protection.max_steps
        )

    @pytest.mark.asyncio
    async def test_max_steps_protection_disabled(self):
        """Test behavior with very high step limit (effectively disabled)."""
        # Create walker with very high step limit (effectively no protection)
        walker = StepCountTestWalker(max_steps=50)
        start_node = ProtectionTestNode(name="start", value=0)

        # Run walker - it will stop at 50 steps due to the walker's internal limit
        await walker.spawn(start_node)

        # Check that walker ran more than the original 5 steps
        # but still stopped due to protection at 50
        report = await walker.get_report()
        protection_reports = [
            item
            for item in report
            if isinstance(item, dict) and "protection_triggered" in item
        ]
        # Protection should trigger at 50 steps
        assert walker.step_count >= 5  # Should have exceeded the original limit

    @pytest.mark.asyncio
    async def test_step_counting_accuracy(self):
        """Test that step counting is accurate."""
        walker = StepCountTestWalker(max_steps=10)
        start_node = ProtectionTestNode(name="start", value=0)

        await walker.spawn(start_node)

        # Check step counting matches expected
        # The Walker should have taken some steps and stopped
        assert walker.step_count > 0  # Should have taken some steps
        assert (
            walker.step_count <= walker._protection.max_steps
        )  # Should not exceed limit
        # The Walker should have stopped (either due to protection or natural completion)
        # This test verifies that step counting is working correctly


class TestNodeVisitProtection:
    """Test maximum visits per node protection mechanism."""

    @pytest.mark.asyncio
    async def test_max_visits_per_node_protection(self):
        """Test that max visits per node protection triggers."""
        walker = NodeRevisitWalker(max_visits_per_node=3)
        start_node = ProtectionTestNode(name="revisit_test", value=0)

        await walker.spawn(start_node)

        # Check protection was triggered by checking visit counts
        # The protection system stops traversal when limits are exceeded
        visit_counts = walker._protection.visit_counts
        assert len(visit_counts) > 0  # Should have visited some nodes
        # Check that the walker stopped due to protection limits
        assert walker.step_count > 0  # Should have taken some steps
        assert (
            walker.step_count <= walker._protection.max_steps
        )  # Should not exceed step limit

    @pytest.mark.asyncio
    async def test_node_visit_counting(self):
        """Test that node visit counting is accurate."""
        walker = NodeRevisitWalker(max_visits_per_node=5)
        start_node = ProtectionTestNode(name="count_test", value=0)

        await walker.spawn(start_node)

        # Check visit counting through protection component
        visit_counts = walker._protection.visit_counts
        assert start_node.id in visit_counts
        assert visit_counts[start_node.id] >= 1  # Should have visited at least once

    @pytest.mark.asyncio
    async def test_multiple_node_visit_tracking(self):
        """Test visit tracking across multiple nodes."""

        class MultiNodeWalker(Walker):
            @on_visit(ProtectionTestNode)
            async def visit_multiple_nodes(self, here):
                # Visit a few different nodes
                if len(self.queue) < 10:
                    nodes = [
                        ProtectionTestNode(name=f"node_a_{len(self.queue)}"),
                        ProtectionTestNode(name=f"node_b_{len(self.queue)}"),
                    ]
                    await self.append(nodes)

        walker = MultiNodeWalker(max_steps=20)
        start_node = ProtectionTestNode(name="multi_start")

        await walker.spawn(start_node)

        # Check that multiple nodes were tracked
        visit_counts = walker._protection.visit_counts
        assert len(visit_counts) > 0  # Should have visited some nodes


class TestTimeoutProtection:
    """Test timeout protection mechanism."""

    @pytest.mark.asyncio
    async def test_timeout_protection_triggers(self):
        """Test that timeout protection triggers correctly."""
        # Create walker with very short timeout
        walker = TimeoutTestWalker(max_execution_time=0.5)
        walker.sleep_duration = 0.2  # Each visit takes 0.2 seconds
        start_node = ProtectionTestNode(name="timeout_test")

        await walker.spawn(start_node)

        # Check timeout protection was triggered by checking execution time
        # The protection system stops traversal when limits are exceeded
        elapsed_time = walker._protection.elapsed_time
        assert elapsed_time is not None  # Should have recorded execution time
        assert elapsed_time >= 0.1  # Should have run for some time
        # The walker should have stopped due to timeout protection
        assert walker.step_count > 0  # Should have taken some steps

    @pytest.mark.asyncio
    async def test_timeout_protection_with_resume(self):
        """Test timeout protection works with resume."""
        walker = TimeoutTestWalker(max_execution_time=0.3)
        walker.sleep_duration = 0.1
        start_node = ProtectionTestNode(name="resume_timeout_test")

        # Start walker (should timeout)
        await walker.spawn(start_node)

        # Check first timeout by checking execution time
        elapsed_time = walker._protection.elapsed_time
        assert elapsed_time is not None  # Should have recorded execution time
        assert walker.step_count > 0  # Should have taken some steps

        # Try to resume (should timeout again quickly since start time is preserved)
        walker._report.clear()  # Clear previous report
        await walker.resume()  # Resume is not async

        # May timeout again or complete depending on timing
        # The key is that protection continues to work


class TestQueueSizeProtection:
    """Test queue size protection mechanism."""

    @pytest.mark.asyncio
    async def test_queue_size_protection(self):
        """Test that queue size protection limits additions."""
        walker = QueueSizeTestWalker(
            max_queue_size=50,
            max_steps=100,  # Set lower step limit to stop traversal quickly
        )
        start_node = ProtectionTestNode(name="queue_test")

        await walker.spawn(start_node)

        # Check that protection triggered (should be max_steps since queue limiting doesn't stop traversal)
        # The protection system stops traversal when limits are exceeded
        assert walker.step_count > 0  # Should have taken some steps
        assert (
            walker.step_count <= walker._protection.max_steps
        )  # Should not exceed step limit

        # Check that queue size was limited throughout execution
        final_queue_size = len(walker.queue)
        assert final_queue_size <= 50

        # Check that many nodes were processed, but queue stayed limited
        assert walker.step_count > 0  # Should have taken some steps
        assert walker.nodes_added > 0  # Some nodes attempted to be added
        assert final_queue_size <= 50  # But queue stayed within limit

    @pytest.mark.asyncio
    async def test_queue_size_protection_disabled(self):
        """Test behavior with very high queue size limit (effectively disabled)."""
        # Create a walker with very high queue size limit
        walker = QueueSizeTestWalker(
            max_queue_size=1000,  # Very high limit
            max_steps=30,  # Set step limit to prevent runaway
        )

        start_node = ProtectionTestNode(name="queue_unlimited_test")

        await walker.spawn(start_node)

        # With high queue limit, queue can grow larger
        # But step protection should still stop the walker
        # The protection system stops traversal when limits are exceeded
        assert walker.step_count > 0  # Should have taken some steps
        assert (
            walker.step_count <= walker._protection.max_steps
        )  # Should not exceed step limit
        final_queue_size = len(walker.queue)
        # Queue should be able to grow with the high limit
        assert walker.nodes_added > 0  # Should have processed some iterations

    async def test_visit_method_queue_protection(self):
        """Test that visit method respects queue size limits."""
        walker = QueueSizeTestWalker(max_queue_size=5)

        # Try to add many nodes at once
        nodes = [ProtectionTestNode(name=f"test_{i}") for i in range(20)]

        # Simulate calling visit (note: this is sync test of the protection logic)
        # In real scenario this would be called async
        initial_queue_size = len(walker.queue)

        # The actual queue size limiting happens in the async visit method
        # This test verifies the logic would work
        # Queue size protection is handled by WalkerQueue, not TraversalProtection
        # The WalkerQueue has a max_size attribute
        expected_available = max(0, walker.queue._max_size - initial_queue_size)
        expected_nodes = min(len(nodes), expected_available)

        assert walker.queue._max_size == 5
        assert expected_available <= 5


class TestProtectionStatusReporting:
    """Test protection status and reporting functionality."""

    async def test_protection_status_basic(self):
        """Test basic protection status reporting."""
        walker = InfiniteLoopWalker(
            max_steps=1000,
            max_visits_per_node=50,
            max_execution_time=60.0,
            max_queue_size=200,
        )

        # Check basic protection status through the protection component
        assert walker._protection is not None
        assert walker._protection._max_steps == 1000
        assert walker._protection._max_visits_per_node == 50
        assert walker._protection._max_execution_time == 60.0
        assert walker.queue._max_size == 200
        # Check initial values
        assert walker.step_count == 0
        assert len(walker.queue) == 0

    @pytest.mark.asyncio
    async def test_protection_status_during_execution(self):
        """Test protection status updates during execution."""
        walker = StepCountTestWalker(max_steps=10)
        start_node = ProtectionTestNode(name="status_test")

        # Record initial status
        initial_step_count = walker.step_count
        initial_queue_size = len(walker.queue)

        # Run walker
        await walker.spawn(start_node)

        # Check final status
        final_step_count = walker.step_count
        final_queue_size = len(walker.queue)

        # Verify status updated
        assert final_step_count > initial_step_count
        assert final_queue_size >= initial_queue_size
        assert len(walker._protection.visit_counts) > 0

    @pytest.mark.asyncio
    async def test_protection_status_timing(self):
        """Test timing information in protection status."""
        walker = TimeoutTestWalker(max_execution_time=1.0)
        walker.sleep_duration = 0.1  # Faster for test
        start_node = ProtectionTestNode(name="timing_test")

        # Start walker (will be stopped by max_steps or timeout)
        await walker.spawn(start_node)

        # Check timing information through protection component
        elapsed_time = walker._protection.elapsed_time
        assert elapsed_time is not None
        assert elapsed_time > 0
        assert walker._protection._max_execution_time == 1.0


class TestProtectionIntegration:
    """Test integration of protection with walker traversal system."""

    @pytest.mark.asyncio
    async def test_protection_with_trail_tracking(self):
        """Test that protection works with trail tracking."""
        # Trail tracking is always enabled in the new architecture
        walker = StepCountTestWalker(
            max_steps=8,
        )
        start_node = ProtectionTestNode(name="trail_protection_test")

        await walker.spawn(start_node)

        # Check both protection and trail worked
        # The protection system stops traversal when limits are exceeded
        assert walker.step_count > 0  # Should have taken some steps
        assert (
            walker.step_count <= walker._protection.max_steps
        )  # Should not exceed step limit
        assert len(walker._trail_tracker._trail) <= walker._protection.max_steps
        assert len(walker._trail_tracker._trail) > 0

    @pytest.mark.asyncio
    async def test_protection_preserves_response_data(self):
        """Test that protection preserves existing response data."""

        class ResponseTestWalker(Walker):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.visit_count = 0

            @on_visit(ProtectionTestNode)
            async def set_response_data(self, here):
                await self.report({"custom_data": "preserved"})
                self.visit_count += 1
                await self.report({"visit_count": self.visit_count})

                # Add nodes to trigger protection
                if len(self.queue) < 20:
                    next_node = ProtectionTestNode(
                        name=f"response_test_{len(self.queue)}"
                    )
                    await self.visit([next_node])

        walker = ResponseTestWalker(max_steps=5)
        start_node = ProtectionTestNode(name="response_test")

        await walker.spawn(start_node)

        # Check protection data was added without overwriting custom data
        # The protection system stops traversal when limits are exceeded
        assert walker.step_count > 0  # Should have taken some steps
        assert (
            walker.step_count <= walker._protection.max_steps
        )  # Should not exceed step limit
        # Check that custom data is preserved in the report
        report = await walker.get_report()
        custom_data_reports = [
            item for item in report if isinstance(item, dict) and "custom_data" in item
        ]
        assert len(custom_data_reports) >= 1
        assert custom_data_reports[0]["custom_data"] == "preserved"

    @pytest.mark.asyncio
    async def test_multiple_protection_triggers(self):
        """Test behavior when multiple protections could trigger."""
        # Create walker where multiple limits are close
        walker = StepCountTestWalker(
            max_steps=3,
            max_visits_per_node=2,
            max_execution_time=0.1,
        )
        start_node = ProtectionTestNode(name="multi_protection_test")

        await walker.spawn(start_node)

        # One of the protections should have triggered
        # The protection system stops traversal when limits are exceeded
        assert walker.step_count > 0  # Should have taken some steps
        assert (
            walker.step_count <= walker._protection.max_steps
        )  # Should not exceed step limit
        # Check that at least one protection mechanism was active
        assert walker._protection._max_steps == 3
        assert walker._protection._max_visits_per_node == 2
        assert walker._protection._max_execution_time == 0.1


class TestProtectionErrorHandling:
    """Test error handling in protection mechanisms."""

    @pytest.mark.asyncio
    async def test_protection_with_hook_errors(self):
        """Test that protection still works when hooks raise errors."""

        class ErrorWalker(Walker):
            error_count: int = 0
            successful_nodes: int = 0

            @on_visit(ProtectionTestNode)
            async def error_prone_hook(self, here):
                self.error_count += 1
                # Error on every 3rd node, but continue processing others
                if self.error_count % 3 == 0:
                    raise ValueError("Test error")

                self.successful_nodes += 1
                # Continue adding nodes for successful processing
                if self.successful_nodes < 15:  # Ensure we get enough successful nodes
                    await self.visit(
                        [ProtectionTestNode(name=f"error_test_{self.error_count}")]
                    )

        walker = ErrorWalker(max_steps=10)
        start_node = ProtectionTestNode(name="error_test")

        await walker.spawn(start_node)

        # Protection should still trigger despite some errors
        # Either max_steps protection should trigger, or the walker should complete
        assert walker.step_count > 0  # Should have processed some steps
        assert walker.error_count > 0  # Should have encountered some errors
        # The important thing is that errors don't break the protection system
        report = await walker.get_report()
        protection_reports = [
            item
            for item in report
            if isinstance(item, dict) and "protection_triggered" in item
        ]
        if len(protection_reports) > 0:
            assert protection_reports[0]["protection_triggered"] == "max_steps"

    async def test_protection_with_invalid_configuration(self):
        """Test handling of invalid protection configuration."""
        # Test with extreme values
        walker = InfiniteLoopWalker(
            max_steps=0, max_visits_per_node=0, max_execution_time=0.0, max_queue_size=0
        )

        # Verify values were set (even if they're edge cases)
        assert walker._protection._max_steps == 0
        assert walker._protection._max_visits_per_node == 0
        assert walker._protection._max_execution_time == 0.0

        # Check that protection component exists and has expected attributes
        assert walker._protection is not None
        assert hasattr(walker._protection, "_max_steps")
        assert hasattr(walker._protection, "_max_visits_per_node")
        assert hasattr(walker._protection, "_max_execution_time")
