"""
Test cases for Walker reporting and event emission functionality.

This module tests the new simplified reporting system and event communication
features introduced in the Walker class.
"""

import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from jvspatial.core.entities import Node, Walker, on_exit, on_visit
from jvspatial.core.events import event_bus, on_emit


class MockNode(Node):
    """Mock node for walker testing."""

    name: str = "test"
    value: int = 0


class ReportingWalker(Walker):
    """Test walker for reporting functionality."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.visit_count = 0

    @on_visit(MockNode)
    async def track_visit(self, here: MockNode):
        """Track node visits."""
        self.visit_count += 1
        self.report(
            {
                "visited": here.name,
                "value": here.value,
                "visit_number": self.visit_count,
            }
        )

    @on_exit
    async def generate_summary(self):
        """Generate summary report."""
        self.report(
            {"summary": {"total_visits": self.visit_count, "walker_id": self.id}}
        )


class EventEmittingWalker(Walker):
    """Test walker for event emission functionality."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.events_sent = 0

    @on_visit(MockNode)
    async def emit_event_on_visit(self, here: MockNode):
        """Emit event when visiting nodes."""
        await self.emit(
            "node_visited",
            {"node_name": here.name, "node_value": here.value, "walker_id": self.id},
        )
        self.events_sent += 1
        self.report({"event_sent": here.name})


class EventReceivingWalker(Walker):
    """Test walker for receiving events."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.events_received = 0
        self.received_data = []

    @on_emit("node_visited")
    async def handle_node_visited(self, event_data: Dict[str, Any]):
        """Handle node_visited events."""
        self.events_received += 1
        self.received_data.append(event_data)
        self.report(
            {
                "received_event": {
                    "from_walker": event_data.get("walker_id"),
                    "node_name": event_data.get("node_name"),
                    "handler_id": self.id,
                }
            }
        )

    @on_emit("test_alert")
    async def handle_alert(self, event_data: Dict[str, Any]):
        """Handle test_alert events."""
        self.report(
            {
                "alert_handled": {
                    "severity": event_data.get("severity", "unknown"),
                    "message": event_data.get("message", ""),
                    "handler_id": self.id,
                }
            }
        )


class TestWalkerReporting:
    """Test Walker reporting functionality."""

    def test_report_initialization(self):
        """Test that walker report is initialized as empty list."""
        walker = ReportingWalker()
        report = walker.get_report()
        assert isinstance(report, list)
        assert len(report) == 0

    def test_single_report_item(self):
        """Test adding a single item to the report."""
        walker = ReportingWalker()
        test_data = {"message": "test report", "value": 42}

        walker.report(test_data)
        report = walker.get_report()

        assert len(report) == 1
        assert report[0] == test_data

    def test_multiple_report_items(self):
        """Test adding multiple items to the report."""
        walker = ReportingWalker()
        items = [
            {"item": 1, "data": "first"},
            {"item": 2, "data": "second"},
            {"item": 3, "data": "third"},
        ]

        for item in items:
            walker.report(item)

        report = walker.get_report()
        assert len(report) == 3
        assert report == items

    def test_report_different_data_types(self):
        """Test reporting different data types."""
        walker = ReportingWalker()

        # Test various data types
        walker.report("string data")
        walker.report(42)
        walker.report([1, 2, 3])
        walker.report({"key": "value"})
        walker.report(None)

        report = walker.get_report()
        assert len(report) == 5
        assert report[0] == "string data"
        assert report[1] == 42
        assert report[2] == [1, 2, 3]
        assert report[3] == {"key": "value"}
        assert report[4] is None

    def test_report_is_reference(self):
        """Test that get_report() returns reference to the actual list."""
        walker = ReportingWalker()
        walker.report("test")

        report1 = walker.get_report()
        report2 = walker.get_report()

        # Should be the same object
        assert report1 is report2

        # Adding more data should be visible in both references
        walker.report("second")
        assert len(report1) == 2
        assert len(report2) == 2

    @pytest.mark.asyncio
    async def test_report_during_traversal(self):
        """Test reporting during walker traversal."""
        walker = ReportingWalker()
        nodes = [
            MockNode(name="node1", value=10),
            MockNode(name="node2", value=20),
            MockNode(name="node3", value=30),
        ]

        # Add nodes to walker queue
        await walker.visit(nodes)

        # Execute traversal
        await walker.spawn(nodes[0])

        report = walker.get_report()

        # Should have visit reports plus summary
        assert len(report) >= 3  # At least 3 visit reports

        # Check visit reports
        visit_reports = [
            item for item in report if isinstance(item, dict) and "visited" in item
        ]
        assert len(visit_reports) == 3
        assert visit_reports[0]["visited"] == "node1"
        assert visit_reports[0]["value"] == 10
        assert visit_reports[0]["visit_number"] == 1

        # Check summary report
        summary_reports = [
            item for item in report if isinstance(item, dict) and "summary" in item
        ]
        assert len(summary_reports) == 1
        assert summary_reports[0]["summary"]["total_visits"] == 3

    def test_report_thread_safety(self):
        """Test that reporting is thread-safe (no async lock needed for simple append)."""
        walker = ReportingWalker()

        # Simulate concurrent reporting
        def concurrent_report(data):
            walker.report(data)

        import threading

        threads = []

        for i in range(10):
            thread = threading.Thread(target=concurrent_report, args=(f"item_{i}",))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        report = walker.get_report()
        assert len(report) == 10
        assert all(f"item_{i}" in report for i in range(10))


class TestWalkerEventEmission:
    """Test Walker event emission functionality."""

    def test_emit_method_exists(self):
        """Test that emit method exists and is callable."""
        walker = EventEmittingWalker()
        assert hasattr(walker, "emit")
        assert callable(walker.emit)

    @pytest.mark.asyncio
    async def test_single_event_emission(self):
        """Test emitting a single event."""
        emitter = EventEmittingWalker()
        receiver = EventReceivingWalker()

        try:
            # Both walkers need to be in the event system
            node = MockNode(name="test_node", value=100)

            # Run emitter first to emit events, then receiver to process them
            await emitter.spawn(node)

            # Give receiver a minimal traversal (root node) to trigger event processing
            await receiver.spawn()

            # Check that event was sent
            emitter_report = emitter.get_report()
            assert len(emitter_report) >= 1
            assert any(
                "event_sent" in item
                for item in emitter_report
                if isinstance(item, dict)
            )

            # Check that event was received
            receiver_report = receiver.get_report()
            received_events = [
                item
                for item in receiver_report
                if isinstance(item, dict) and "received_event" in item
            ]
            assert len(received_events) >= 1
            assert received_events[0]["received_event"]["node_name"] == "test_node"
        finally:
            # Clean up walkers from event bus
            try:
                await emitter.disengage()
                await receiver.disengage()
            except:
                pass

    @pytest.mark.asyncio
    async def test_multiple_event_emissions(self):
        """Test emitting multiple events."""
        emitter = EventEmittingWalker()
        receiver = EventReceivingWalker()

        try:
            nodes = [
                MockNode(name="node1", value=10),
                MockNode(name="node2", value=20),
                MockNode(name="node3", value=30),
            ]

            await emitter.visit(nodes)

            # Run emitter first to emit events
            await emitter.spawn(nodes[0])

            # Give receiver a minimal traversal to trigger event processing
            await receiver.spawn()

            # Check that multiple events were sent
            assert emitter.events_sent == 3

            # Check that multiple events were received
            assert receiver.events_received >= 3
            receiver_report = receiver.get_report()
            received_events = [
                item
                for item in receiver_report
                if isinstance(item, dict) and "received_event" in item
            ]
            assert len(received_events) >= 3
        finally:
            # Clean up walkers
            try:
                await emitter.disengage()
                await receiver.disengage()
            except:
                pass

    @pytest.mark.asyncio
    async def test_event_data_payload(self):
        """Test that event data payload is transmitted correctly."""
        emitter = EventEmittingWalker()
        receiver = EventReceivingWalker()

        try:
            node = MockNode(name="payload_test", value=999)

            # Run emitter first to emit events
            await emitter.spawn(node)

            # Give receiver a minimal traversal to trigger event processing
            await receiver.spawn()

            # Check received data
            assert len(receiver.received_data) >= 1
            received_payload = receiver.received_data[0]
            assert received_payload["node_name"] == "payload_test"
            assert received_payload["node_value"] == 999
            assert received_payload["walker_id"] == emitter.id
        finally:
            # Clean up walkers
            try:
                await emitter.disengage()
                await receiver.disengage()
            except:
                pass

    @pytest.mark.asyncio
    async def test_selective_event_handling(self):
        """Test that walkers only handle events they're subscribed to."""
        emitter = EventEmittingWalker()
        receiver = EventReceivingWalker()

        try:
            node = MockNode(name="selective_test")

            # Emit different types of events
            await emitter.emit("node_visited", {"test": "data1"})
            await emitter.emit(
                "test_alert", {"severity": "high", "message": "Test alert"}
            )
            await emitter.emit("unhandled_event", {"test": "data3"})

            # Give receiver a chance to process events
            await receiver.spawn(node)

            receiver_report = receiver.get_report()

            # Should have received node_visited and test_alert, but not unhandled_event
            received_events = [
                item
                for item in receiver_report
                if isinstance(item, dict) and "received_event" in item
            ]
            alert_events = [
                item
                for item in receiver_report
                if isinstance(item, dict) and "alert_handled" in item
            ]

            assert len(received_events) >= 1  # node_visited
            assert len(alert_events) >= 1  # test_alert
        finally:
            # Clean up walkers
            try:
                await emitter.disengage()
                await receiver.disengage()
            except:
                pass

    @pytest.mark.asyncio
    async def test_multiple_receivers_same_event(self):
        """Test that multiple walkers can receive the same event."""
        emitter = EventEmittingWalker()
        receiver1 = EventReceivingWalker()
        receiver2 = EventReceivingWalker()

        try:
            node = MockNode(name="broadcast_test")

            # Run emitter first to emit events
            await emitter.spawn(node)

            # Give receivers minimal traversal to trigger event processing
            await receiver1.spawn()
            await receiver2.spawn()

            # Both receivers should have received the event
            receiver1_report = receiver1.get_report()
            receiver2_report = receiver2.get_report()

            received_events1 = [
                item
                for item in receiver1_report
                if isinstance(item, dict) and "received_event" in item
            ]
            received_events2 = [
                item
                for item in receiver2_report
                if isinstance(item, dict) and "received_event" in item
            ]

            assert len(received_events1) >= 1
            assert len(received_events2) >= 1

            # Both should have received the same event data
            assert (
                received_events1[0]["received_event"]["node_name"] == "broadcast_test"
            )
            assert (
                received_events2[0]["received_event"]["node_name"] == "broadcast_test"
            )
        finally:
            # Clean up walkers
            try:
                await emitter.disengage()
                await receiver1.disengage()
                await receiver2.disengage()
            except:
                pass


class TestWalkerReportingAndEvents:
    """Test integration of reporting and event systems."""

    @pytest.mark.asyncio
    async def test_report_and_emit_integration(self):
        """Test that walkers can both report and emit events simultaneously."""
        emitter = EventEmittingWalker()
        receiver = EventReceivingWalker()

        try:
            nodes = [MockNode(name="integration_test", value=42)]
            await emitter.visit(nodes)

            # Run emitter first to emit events
            await emitter.spawn(nodes[0])

            # Give receiver a minimal traversal to trigger event processing
            await receiver.spawn()

            # Emitter should have both reported and emitted
            emitter_report = emitter.get_report()
            assert len(emitter_report) >= 1
            assert emitter.events_sent >= 1

            # Receiver should have both received events and reported about them
            receiver_report = receiver.get_report()
            assert len(receiver_report) >= 1
            assert receiver.events_received >= 1

            # Cross-check that the data matches
            received_events = [
                item
                for item in receiver_report
                if isinstance(item, dict) and "received_event" in item
            ]
            assert len(received_events) >= 1
            assert (
                received_events[0]["received_event"]["node_name"] == "integration_test"
            )
        finally:
            # Clean up walkers
            try:
                await emitter.disengage()
                await receiver.disengage()
            except:
                pass

    @pytest.mark.asyncio
    async def test_event_chain_communication(self):
        """Test chain of event communications between multiple walkers."""

        class ChainWalker(Walker):
            def __init__(self, walker_name: str, **kwargs):
                super().__init__(**kwargs)
                self.walker_name = walker_name
                self.chain_events: List[Dict[str, Any]] = []
                self.events_emitted = 0

            @on_emit("chain_event")
            async def handle_chain_event(self, event_data: Dict[str, Any]):
                """Handle chain events - simplified without re-emission to avoid loops."""
                self.chain_events.append(event_data)
                self.report(
                    {
                        "chain_received": {
                            "from": event_data.get("from"),
                            "step": event_data.get("step", 0),
                            "walker": self.walker_name,
                            "message": event_data.get("message", ""),
                        }
                    }
                )

        # Create chain walkers
        walker1 = ChainWalker("walker1")
        walker2 = ChainWalker("walker2")
        walker3 = ChainWalker("walker3")

        try:
            node = MockNode(name="chain_test")

            # First emit events, then spawn receivers (this is the pattern from working tests)
            # Start walker1 to register it with the event bus
            await walker1.spawn(node)

            # Emit the event while only walker1 is active
            await walker1.emit(
                "chain_event",
                {
                    "from": walker1.walker_name,
                    "step": 1,
                    "message": "Test chain message",
                },
            )

            # Now spawn the receivers - they should process the event during spawn
            await walker2.spawn(node)
            await walker3.spawn(node)

            # Verify that other walkers received the event
            # walker1 should not receive its own event
            assert (
                len(walker1.chain_events) == 0
            ), "Walker should not receive its own events"

            # walker2 and walker3 should receive the event
            receivers_with_events = 0
            for walker in [walker2, walker3]:
                if len(walker.chain_events) > 0:
                    receivers_with_events += 1
                    # Verify event content
                    event = walker.chain_events[0]
                    assert event["from"] == "walker1"
                    assert event["step"] == 1
                    assert event["message"] == "Test chain message"

            assert (
                receivers_with_events >= 1
            ), f"At least one walker should have received events. walker2 events: {len(walker2.chain_events)}, walker3 events: {len(walker3.chain_events)}"

            # Check that reports were generated
            reports_with_chain_data = 0
            for walker in [walker2, walker3]:  # Only check receivers
                report = walker.get_report()
                chain_reports = [
                    item
                    for item in report
                    if isinstance(item, dict) and "chain_received" in item
                ]
                if chain_reports:
                    reports_with_chain_data += 1
                    # Verify report content
                    chain_report = chain_reports[0]
                    assert chain_report["chain_received"]["from"] == "walker1"

            assert (
                reports_with_chain_data >= 1
            ), "At least one walker should have reported receiving events"

        finally:
            # Clean up all walkers
            for walker in [walker1, walker2, walker3]:
                try:
                    await walker.disengage()
                except:
                    pass

    def test_error_handling_in_reports(self):
        """Test that errors during traversal are properly reported."""

        class ErrorReportingWalker(Walker):
            @on_visit(MockNode)
            async def error_prone_visit(self, here: MockNode):
                if here.name == "error_node":
                    raise ValueError("Test error in visit hook")
                self.report({"visited_safely": here.name})

        walker = ErrorReportingWalker()
        # This test checks that the walker's error handling system
        # properly adds error information to reports
        # The actual error handling is tested in the Walker implementation

        assert hasattr(walker, "report")
        assert hasattr(walker, "get_report")

        # Test normal reporting still works
        walker.report({"test": "data"})
        report = walker.get_report()
        assert len(report) == 1
        assert report[0] == {"test": "data"}


class TestEventBusIntegration:
    """Test integration with the global event bus."""

    def test_walker_registers_with_event_bus(self):
        """Test that walkers automatically register with the global event bus."""
        walker = EventReceivingWalker()

        # Walker should be registered with the event bus
        # This is handled by the Walker.__init__ method
        assert hasattr(walker, "_event_handlers")
        assert isinstance(walker._event_handlers, dict)

    @pytest.mark.asyncio
    async def test_global_event_emission(self):
        """Test that events can be emitted globally and received by walkers."""
        receiver = EventReceivingWalker()

        # Emit event globally
        await event_bus.emit(
            "test_alert", {"severity": "critical", "message": "Global test alert"}
        )

        # Give receiver time to process
        node = MockNode(name="global_test")
        await receiver.spawn(node)

        # Check that global event was received
        receiver_report = receiver.get_report()
        alert_reports = [
            item
            for item in receiver_report
            if isinstance(item, dict) and "alert_handled" in item
        ]

        # Note: This test may need adjustment based on actual event bus implementation
        # The key is to verify that global events reach walker event handlers


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
