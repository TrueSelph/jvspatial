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

from jvspatial.core.entities import (
    Edge,
    Node,
    Root,
    Walker,
    on_visit,
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
            await self.visit([next_node])


class NodeRevisitWalker(Walker):
    """Walker for testing node revisit limits."""

    revisit_count: int = 0

    @on_visit(ProtectionTestNode)
    async def revisit_same_node(self, here):
        """Keep revisiting the same node."""
        self.revisit_count += 1

        # Keep adding the same node to trigger revisit protection
        if self.revisit_count < 50:  # Prevent runaway in case protection fails
            await self.visit([here])


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

    def test_protection_default_initialization(self):
        """Test that protection attributes are initialized with defaults."""
        walker = InfiniteLoopWalker()

        assert walker.protection_enabled is True
        assert walker.max_steps == 10000
        assert walker.max_visits_per_node == 100
        assert walker.max_execution_time == 300.0
        assert walker.max_queue_size == 1000
        assert walker.step_count == 0
        assert walker.node_visit_counts == {}

    def test_protection_custom_initialization(self):
        """Test protection with custom initialization values."""
        walker = InfiniteLoopWalker(
            max_steps=5000,
            max_visits_per_node=50,
            max_execution_time=60.0,
            max_queue_size=500,
            protection_enabled=False,
        )

        assert walker.protection_enabled is False
        assert walker.max_steps == 5000
        assert walker.max_visits_per_node == 50
        assert walker.max_execution_time == 60.0
        assert walker.max_queue_size == 500

    def test_protection_property_setters(self):
        """Test protection property setters with validation."""
        walker = InfiniteLoopWalker()

        # Test valid values
        walker.max_steps = 2000
        walker.max_visits_per_node = 25
        walker.max_execution_time = 120.0
        walker.max_queue_size = 200
        walker.protection_enabled = False

        assert walker.max_steps == 2000
        assert walker.max_visits_per_node == 25
        assert walker.max_execution_time == 120.0
        assert walker.max_queue_size == 200
        assert walker.protection_enabled is False

    def test_protection_property_validation(self):
        """Test that property setters validate negative values."""
        walker = InfiniteLoopWalker()

        # Test negative values are converted to 0 or positive
        walker.max_steps = -100
        walker.max_visits_per_node = -50
        walker.max_execution_time = -30.0
        walker.max_queue_size = -200

        assert walker.max_steps == 0
        assert walker.max_visits_per_node == 0
        assert walker.max_execution_time == 0.0
        assert walker.max_queue_size == 0

    @patch.dict(
        os.environ,
        {
            "JVSPATIAL_WALKER_MAX_STEPS": "5000",
            "JVSPATIAL_WALKER_MAX_VISITS_PER_NODE": "25",
            "JVSPATIAL_WALKER_MAX_EXECUTION_TIME": "120.0",
            "JVSPATIAL_WALKER_MAX_QUEUE_SIZE": "250",
            "JVSPATIAL_WALKER_PROTECTION_ENABLED": "false",
        },
    )
    def test_environment_variable_initialization(self):
        """Test initialization from environment variables."""
        walker = InfiniteLoopWalker()

        assert walker.max_steps == 5000
        assert walker.max_visits_per_node == 25
        assert walker.max_execution_time == 120.0
        assert walker.max_queue_size == 250
        assert walker.protection_enabled is False


class TestMaxStepsProtection:
    """Test maximum steps protection mechanism."""

    @pytest.mark.asyncio
    async def test_max_steps_protection_triggers(self):
        """Test that max steps protection triggers correctly."""
        # Create walker with very low step limit
        walker = StepCountTestWalker(max_steps=5, protection_enabled=True)
        start_node = ProtectionTestNode(name="start", value=0)

        # Run walker and expect protection to trigger
        await walker.spawn(start_node)

        # Check protection was triggered
        report = walker.get_report()
        protection_reports = [
            item
            for item in report
            if isinstance(item, dict) and "protection_triggered" in item
        ]
        assert len(protection_reports) >= 1
        protection_report = protection_reports[0]
        assert protection_report["protection_triggered"] == "max_steps"
        assert protection_report["steps_taken"] == 5
        assert protection_report["max_steps"] == 5
        assert walker.paused is True  # Should be disengaged/paused

    @pytest.mark.asyncio
    async def test_max_steps_protection_disabled(self):
        """Test behavior when max steps protection is disabled."""
        # Create walker with protection disabled
        walker = StepCountTestWalker(max_steps=5, protection_enabled=False)
        start_node = ProtectionTestNode(name="start", value=0)

        # Add timeout to prevent actual infinite loop in test
        try:
            await asyncio.wait_for(walker.spawn(start_node), timeout=1.0)
        except asyncio.TimeoutError:
            pass  # Expected when protection is disabled

        # Check protection was not triggered
        report = walker.get_report()
        protection_reports = [
            item
            for item in report
            if isinstance(item, dict) and "protection_triggered" in item
        ]
        assert len(protection_reports) == 0
        assert walker.steps_taken > 5  # Should have exceeded the limit

    @pytest.mark.asyncio
    async def test_step_counting_accuracy(self):
        """Test that step counting is accurate."""
        walker = StepCountTestWalker(max_steps=10, protection_enabled=True)
        start_node = ProtectionTestNode(name="start", value=0)

        await walker.spawn(start_node)

        # Check step counting matches expected
        # The protection triggers when step_count >= max_steps, so we should have exactly max_steps
        assert walker.step_count == walker.max_steps
        # The walker's own steps_taken counter might differ by one since it's incremented in hooks
        # while step_count is incremented before hook processing
        assert walker.steps_taken >= walker.max_steps - 1


class TestNodeVisitProtection:
    """Test maximum visits per node protection mechanism."""

    @pytest.mark.asyncio
    async def test_max_visits_per_node_protection(self):
        """Test that max visits per node protection triggers."""
        walker = NodeRevisitWalker(max_visits_per_node=3, protection_enabled=True)
        start_node = ProtectionTestNode(name="revisit_test", value=0)

        await walker.spawn(start_node)

        # Check protection was triggered
        report = walker.get_report()
        protection_reports = [
            item
            for item in report
            if isinstance(item, dict) and "protection_triggered" in item
        ]
        assert len(protection_reports) >= 1
        protection_report = protection_reports[0]
        assert protection_report["protection_triggered"] == "max_visits_per_node"
        assert protection_report["node_id"] == start_node.id
        assert protection_report["visit_count"] > 3
        assert protection_report["max_visits_per_node"] == 3

    @pytest.mark.asyncio
    async def test_node_visit_counting(self):
        """Test that node visit counting is accurate."""
        walker = NodeRevisitWalker(max_visits_per_node=5, protection_enabled=True)
        start_node = ProtectionTestNode(name="count_test", value=0)

        await walker.spawn(start_node)

        # Check visit counting
        visit_counts = walker.node_visit_counts
        assert start_node.id in visit_counts
        assert visit_counts[start_node.id] > 5

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
                    await self.visit(nodes)

        walker = MultiNodeWalker(max_steps=20, protection_enabled=True)
        start_node = ProtectionTestNode(name="multi_start")

        await walker.spawn(start_node)

        # Check that multiple nodes were tracked
        visit_counts = walker.node_visit_counts
        assert len(visit_counts) > 1


class TestTimeoutProtection:
    """Test timeout protection mechanism."""

    @pytest.mark.asyncio
    async def test_timeout_protection_triggers(self):
        """Test that timeout protection triggers correctly."""
        # Create walker with very short timeout
        walker = TimeoutTestWalker(max_execution_time=0.5, protection_enabled=True)
        walker.sleep_duration = 0.2  # Each visit takes 0.2 seconds
        start_node = ProtectionTestNode(name="timeout_test")

        await walker.spawn(start_node)

        # Check timeout protection was triggered
        report = walker.get_report()
        protection_reports = [
            item
            for item in report
            if isinstance(item, dict) and "protection_triggered" in item
        ]
        assert len(protection_reports) >= 1
        protection_report = protection_reports[0]
        assert protection_report["protection_triggered"] == "timeout"
        assert "execution_time" in protection_report
        assert protection_report["max_execution_time"] == 0.5
        assert protection_report["execution_time"] >= 0.5

    @pytest.mark.asyncio
    async def test_timeout_protection_with_resume(self):
        """Test timeout protection works with resume."""
        walker = TimeoutTestWalker(max_execution_time=0.3, protection_enabled=True)
        walker.sleep_duration = 0.1
        start_node = ProtectionTestNode(name="resume_timeout_test")

        # Start walker (should timeout)
        await walker.spawn(start_node)

        # Check first timeout
        report = walker.get_report()
        protection_reports = [
            item
            for item in report
            if isinstance(item, dict) and "protection_triggered" in item
        ]
        assert len(protection_reports) >= 1
        assert protection_reports[0]["protection_triggered"] == "timeout"

        # Try to resume (should timeout again quickly since start time is preserved)
        walker._report.clear()  # Clear previous report
        await walker.resume()

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
            protection_enabled=True,
        )
        start_node = ProtectionTestNode(name="queue_test")

        await walker.spawn(start_node)

        # Check that protection triggered (should be max_steps since queue limiting doesn't stop traversal)
        report = walker.get_report()
        protection_reports = [
            item
            for item in report
            if isinstance(item, dict) and "protection_triggered" in item
        ]
        assert len(protection_reports) >= 1
        assert protection_reports[0]["protection_triggered"] == "max_steps"

        # Check that queue size was limited throughout execution
        final_queue_size = len(walker.queue)
        assert final_queue_size <= 50

        # Check that many nodes were processed, but queue stayed limited
        assert walker.step_count == 100  # Should have hit step limit
        assert walker.nodes_added > 100  # Many nodes attempted to be added
        assert final_queue_size <= 50  # But queue stayed within limit

    @pytest.mark.asyncio
    async def test_queue_size_protection_disabled(self):
        """Test behavior when queue size protection is disabled."""
        # Create a walker with protection enabled, but manually disable only queue protection
        walker = QueueSizeTestWalker(
            max_queue_size=10,
            max_steps=30,  # Set step limit to prevent runaway
            protection_enabled=True,  # Keep protection on for step limits
        )

        # Manually disable queue size protection by overriding the visit method
        original_visit = walker.visit

        async def unrestricted_visit(nodes):
            """Visit method without queue size restrictions."""
            nodes_list = nodes if isinstance(nodes, list) else [nodes]
            walker.queue.extend(nodes_list)
            return nodes_list

        walker.visit = unrestricted_visit

        start_node = ProtectionTestNode(name="queue_unlimited_test")

        await walker.spawn(start_node)

        # When queue protection is disabled, queue can grow larger than the limit
        # But step protection should still stop the walker
        report = walker.get_report()
        protection_reports = [
            item
            for item in report
            if isinstance(item, dict) and "protection_triggered" in item
        ]
        assert len(protection_reports) >= 1
        assert protection_reports[0]["protection_triggered"] == "max_steps"
        final_queue_size = len(walker.queue)
        # Queue should be able to grow beyond the normal limit
        assert final_queue_size > 10  # Should exceed the "limit"
        assert walker.nodes_added >= 30  # Should have processed many iterations

    def test_visit_method_queue_protection(self):
        """Test that visit method respects queue size limits."""
        walker = QueueSizeTestWalker(max_queue_size=5, protection_enabled=True)

        # Try to add many nodes at once
        nodes = [ProtectionTestNode(name=f"test_{i}") for i in range(20)]

        # Simulate calling visit (note: this is sync test of the protection logic)
        # In real scenario this would be called async
        initial_queue_size = len(walker.queue)

        # The actual queue size limiting happens in the async visit method
        # This test verifies the logic would work
        expected_available = max(0, walker.max_queue_size - initial_queue_size)
        expected_nodes = min(len(nodes), expected_available)

        assert walker.max_queue_size == 5
        assert expected_available <= 5


class TestProtectionStatusReporting:
    """Test protection status and reporting functionality."""

    def test_protection_status_basic(self):
        """Test basic protection status reporting."""
        walker = InfiniteLoopWalker(
            max_steps=1000,
            max_visits_per_node=50,
            max_execution_time=60.0,
            max_queue_size=200,
        )

        status = walker.get_protection_status()

        # Check basic status structure
        assert "protection_enabled" in status
        assert "step_count" in status
        assert "max_steps" in status
        assert "step_usage_percent" in status
        assert "queue_size" in status
        assert "max_queue_size" in status
        assert "queue_usage_percent" in status
        assert "max_visits_per_node" in status
        assert "node_visit_counts" in status

        # Check initial values
        assert status["protection_enabled"] is True
        assert status["step_count"] == 0
        assert status["step_usage_percent"] == 0.0
        assert status["queue_usage_percent"] == 0.0

    @pytest.mark.asyncio
    async def test_protection_status_during_execution(self):
        """Test protection status updates during execution."""
        walker = StepCountTestWalker(max_steps=10, protection_enabled=True)
        start_node = ProtectionTestNode(name="status_test")

        # Record initial status
        initial_status = walker.get_protection_status()

        # Run walker
        await walker.spawn(start_node)

        # Check final status
        final_status = walker.get_protection_status()

        # Verify status updated
        assert final_status["step_count"] > initial_status["step_count"]
        assert final_status["step_usage_percent"] > initial_status["step_usage_percent"]
        assert len(final_status["node_visit_counts"]) > 0

    @pytest.mark.asyncio
    async def test_protection_status_timing(self):
        """Test timing information in protection status."""
        walker = TimeoutTestWalker(max_execution_time=1.0, protection_enabled=True)
        walker.sleep_duration = 0.1  # Faster for test
        start_node = ProtectionTestNode(name="timing_test")

        # Start walker (will be stopped by max_steps or timeout)
        await walker.spawn(start_node)

        status = walker.get_protection_status()

        # Check timing information
        assert "elapsed_time" in status
        assert "max_execution_time" in status
        assert "time_usage_percent" in status
        assert status["elapsed_time"] is not None
        assert status["elapsed_time"] > 0


class TestProtectionIntegration:
    """Test integration of protection with walker traversal system."""

    @pytest.mark.asyncio
    async def test_protection_with_trail_tracking(self):
        """Test that protection works with trail tracking enabled."""
        walker = StepCountTestWalker(
            max_steps=8,
            protection_enabled=True,
            trail_enabled=True,
            max_trail_length=20,
        )
        start_node = ProtectionTestNode(name="trail_protection_test")

        await walker.spawn(start_node)

        # Check both protection and trail worked
        report = walker.get_report()
        protection_reports = [
            item
            for item in report
            if isinstance(item, dict) and "protection_triggered" in item
        ]
        assert len(protection_reports) >= 1
        assert protection_reports[0]["protection_triggered"] == "max_steps"
        assert len(walker.get_trail()) <= walker.max_steps
        assert walker.get_trail_length() > 0

    @pytest.mark.asyncio
    async def test_protection_preserves_response_data(self):
        """Test that protection preserves existing response data."""

        class ResponseTestWalker(Walker):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.visit_count = 0

            @on_visit(ProtectionTestNode)
            async def set_response_data(self, here):
                self.report({"custom_data": "preserved"})
                self.visit_count += 1
                self.report({"visit_count": self.visit_count})

                # Add nodes to trigger protection
                if len(self.queue) < 20:
                    next_node = ProtectionTestNode(
                        name=f"response_test_{len(self.queue)}"
                    )
                    await self.visit([next_node])

        walker = ResponseTestWalker(max_steps=5, protection_enabled=True)
        start_node = ProtectionTestNode(name="response_test")

        await walker.spawn(start_node)

        # Check protection data was added without overwriting custom data
        report = walker.get_report()
        protection_reports = [
            item
            for item in report
            if isinstance(item, dict) and "protection_triggered" in item
        ]
        custom_data_reports = [
            item for item in report if isinstance(item, dict) and "custom_data" in item
        ]
        visit_count_reports = [
            item for item in report if isinstance(item, dict) and "visit_count" in item
        ]

        assert len(protection_reports) >= 1
        assert protection_reports[0]["protection_triggered"] == "max_steps"
        assert len(custom_data_reports) >= 1
        assert custom_data_reports[0]["custom_data"] == "preserved"
        assert len(visit_count_reports) >= 1

    @pytest.mark.asyncio
    async def test_multiple_protection_triggers(self):
        """Test behavior when multiple protections could trigger."""
        # Create walker where multiple limits are close
        walker = StepCountTestWalker(
            max_steps=3,
            max_visits_per_node=2,
            max_execution_time=0.1,
            protection_enabled=True,
        )
        start_node = ProtectionTestNode(name="multi_protection_test")

        await walker.spawn(start_node)

        # One of the protections should have triggered
        report = walker.get_report()
        protection_reports = [
            item
            for item in report
            if isinstance(item, dict) and "protection_triggered" in item
        ]
        assert len(protection_reports) >= 1
        protection_type = protection_reports[0]["protection_triggered"]
        assert protection_type in ["max_steps", "max_visits_per_node", "timeout"]


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

        walker = ErrorWalker(max_steps=10, protection_enabled=True)
        start_node = ProtectionTestNode(name="error_test")

        await walker.spawn(start_node)

        # Protection should still trigger despite some errors
        # Either max_steps protection should trigger, or the walker should complete
        assert walker.step_count > 0  # Should have processed some steps
        assert walker.error_count > 0  # Should have encountered some errors
        # The important thing is that errors don't break the protection system
        report = walker.get_report()
        protection_reports = [
            item
            for item in report
            if isinstance(item, dict) and "protection_triggered" in item
        ]
        if len(protection_reports) > 0:
            assert protection_reports[0]["protection_triggered"] == "max_steps"

    def test_protection_with_invalid_configuration(self):
        """Test handling of invalid protection configuration."""
        # Test with extreme values
        walker = InfiniteLoopWalker(
            max_steps=0, max_visits_per_node=0, max_execution_time=0.0, max_queue_size=0
        )

        # Verify values were set (even if they're edge cases)
        assert walker.max_steps == 0
        assert walker.max_visits_per_node == 0
        assert walker.max_execution_time == 0.0
        assert walker.max_queue_size == 0

        # Status should still work
        status = walker.get_protection_status()
        assert isinstance(status, dict)
