#!/usr/bin/env python3
"""
Walker Event Communication Demo

This example demonstrates the new Walker event system that allows
walkers to communicate with each other during traversal using emit() and @on_emit.
"""

import asyncio
from typing import Any, Dict, List

from jvspatial.core import (
    Edge,
    GraphContext,
    Node,
    Root,
    Walker,
    on_emit,
    on_exit,
    on_visit,
)
from jvspatial.core.context import set_default_context
from jvspatial.db import create_database


class AlertNode(Node):
    """A node that can trigger alerts."""

    name: str = ""
    severity: str = "info"
    message: str = ""


class MonitoringWalker(Walker):
    """A walker that monitors nodes and emits alerts."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.alerts_sent = 0

    @on_visit(Root)
    async def visit_root(self, here: Root) -> None:
        """Continue traversal from root to connected AlertNodes."""
        connected_nodes = await here.nodes()
        alert_nodes = [n for n in connected_nodes if isinstance(n, AlertNode)]
        if alert_nodes:
            await self.visit(alert_nodes)

    @on_visit(AlertNode)
    async def check_for_alerts(self, here: AlertNode) -> None:
        """Check if this node should trigger an alert."""
        # Skip if already visited (check trail)
        if self.is_visited(here):
            return

        if here.severity in ["warning", "critical"]:
            await self.emit(
                "alert_detected",
                {
                    "node_id": here.id,
                    "name": here.name,
                    "severity": here.severity,
                    "message": here.message,
                    "walker_id": self.id,
                },
            )
            self.alerts_sent += 1
            await self.report(
                {
                    "alert_sent": {
                        "node": here.name,
                        "severity": here.severity,
                        "message": here.message,
                    }
                }
            )
            print(f"🚨 {self.id}: Alert sent for {here.name} ({here.severity})")

        # Continue traversal to connected nodes (only unvisited ones, check trail)
        connected_nodes = await here.nodes()
        alert_neighbors = [
            n
            for n in connected_nodes
            if isinstance(n, AlertNode) and not self.is_visited(n)
        ]
        if alert_neighbors:
            await self.visit(alert_neighbors)


class LoggingWalker(Walker):
    """A walker that receives and logs events from other walkers."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.events_received = 0

    @on_visit(Root)
    async def visit_root(self, here: Root) -> None:
        """Continue traversal from root to connected AlertNodes."""
        connected_nodes = await here.nodes()
        alert_nodes = [n for n in connected_nodes if isinstance(n, AlertNode)]
        if alert_nodes:
            await self.visit(alert_nodes)

    @on_emit("alert_detected")
    async def handle_alert(
        self, event_type: str, event_data: Dict[str, Any], source_id: str
    ) -> None:
        """Handle alert events from monitoring walkers."""
        self.events_received += 1

        await self.report(
            {
                "received_alert": {
                    "from_walker": event_data.get("walker_id", "unknown"),
                    "node_name": event_data.get("name", "unknown"),
                    "severity": event_data.get("severity", "unknown"),
                    "message": event_data.get("message", ""),
                    "handled_by": self.id,
                }
            }
        )
        print(f"📝 {self.id}: Logged alert from {event_data.get('name', 'unknown')}")

    @on_visit(AlertNode)
    async def log_node_visit(self, here: AlertNode) -> None:
        """Log visits to alert nodes."""
        # Skip if already visited (check trail)
        if self.is_visited(here):
            return

        await self.report(
            {
                "node_visit": {
                    "node": here.name,
                    "severity": here.severity,
                    "walker_id": self.id,
                }
            }
        )
        # Continue traversal to connected nodes (only unvisited ones, check trail)
        connected_nodes = await here.nodes()
        alert_neighbors = [
            n
            for n in connected_nodes
            if isinstance(n, AlertNode) and not self.is_visited(n)
        ]
        if alert_neighbors:
            await self.visit(alert_neighbors)


class AnalyticsWalker(Walker):
    """A walker that analyzes alert patterns."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.alert_counts = {"info": 0, "warning": 0, "critical": 0}

    @on_visit(Root)
    async def visit_root(self, here: Root) -> None:
        """Continue traversal from root to connected AlertNodes."""
        connected_nodes = await here.nodes()
        alert_nodes = [n for n in connected_nodes if isinstance(n, AlertNode)]
        if alert_nodes:
            await self.visit(alert_nodes)

    @on_visit(AlertNode)
    async def visit_alert_node(self, here: AlertNode) -> None:
        """Visit alert nodes to stay synchronized with other walkers."""
        # Skip if already visited (check trail)
        if self.is_visited(here):
            return

        # Continue traversal to connected nodes (only unvisited ones, check trail)
        connected_nodes = await here.nodes()
        alert_neighbors = [
            n
            for n in connected_nodes
            if isinstance(n, AlertNode) and not self.is_visited(n)
        ]
        if alert_neighbors:
            await self.visit(alert_neighbors)

    @on_emit("alert_detected")
    async def analyze_alert(
        self, event_type: str, event_data: Dict[str, Any], source_id: str
    ) -> None:
        """Analyze incoming alerts for patterns."""
        severity = event_data.get("severity", "info")
        self.alert_counts[severity] += 1

        await self.report(
            {
                "alert_analysis": {
                    "severity": severity,
                    "total_by_severity": self.alert_counts[severity],
                    "node": event_data.get("name", "unknown"),
                    "analyzer_id": self.id,
                }
            }
        )
        print(
            f"📊 {self.id}: Analyzed {severity} alert from {event_data.get('name', 'unknown')}"
        )

    @on_exit
    async def generate_alert_summary(self) -> None:
        """Generate final analytics summary."""
        total_alerts = sum(self.alert_counts.values())

        # Emit final summary to other walkers
        summary_data = {
            "total_alerts": total_alerts,
            "by_severity": self.alert_counts,
            "analyzer_id": self.id,
        }

        await self.emit("analytics_complete", summary_data)

        await self.report({"final_summary": summary_data})


class ReportWalker(Walker):
    """A walker that generates final reports based on analytics."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.analytics_received = []

    @on_visit(Root)
    async def visit_root(self, here: Root) -> None:
        """Continue traversal from root to connected AlertNodes."""
        connected_nodes = await here.nodes()
        alert_nodes = [n for n in connected_nodes if isinstance(n, AlertNode)]
        if alert_nodes:
            await self.visit(alert_nodes)

    @on_visit(AlertNode)
    async def visit_alert_node(self, here: AlertNode) -> None:
        """Visit alert nodes to stay synchronized with other walkers."""
        # Skip if already visited (check trail)
        if self.is_visited(here):
            return

        # Continue traversal to connected nodes (only unvisited ones, check trail)
        connected_nodes = await here.nodes()
        alert_neighbors = [
            n
            for n in connected_nodes
            if isinstance(n, AlertNode) and not self.is_visited(n)
        ]
        if alert_neighbors:
            await self.visit(alert_neighbors)

    @on_emit("analytics_complete")
    async def handle_analytics_complete(
        self, event_type: str, event_data: Dict[str, Any], source_id: str
    ) -> None:
        """Handle completion of analytics from other walkers."""
        self.analytics_received.append(event_data)

        await self.report(
            {
                "analytics_received": {
                    "from_analyzer": event_data.get("analyzer_id", "unknown"),
                    "total_alerts": event_data.get("total_alerts", 0),
                    "breakdown": event_data.get("by_severity", {}),
                    "report_walker": self.id,
                }
            }
        )
        print(f"📄 {self.id}: Received analytics summary")


async def create_alert_graph() -> None:
    """Create a sample graph with alert nodes."""
    root = await Root.get()  # type: ignore[call-arg]
    if root is None:
        raise RuntimeError("Could not get root node")

    # Create alert nodes with different severities
    nodes = [
        AlertNode(name="Server1", severity="info", message="Normal operation"),
        AlertNode(name="Database", severity="warning", message="High CPU usage"),
        AlertNode(name="Network", severity="info", message="Traffic normal"),
        AlertNode(name="Storage", severity="critical", message="Disk space low"),
        AlertNode(name="API", severity="warning", message="Slow response times"),
        AlertNode(name="Cache", severity="info", message="Hit rate good"),
        AlertNode(name="Queue", severity="critical", message="Backlog growing"),
    ]

    # Save all nodes
    for node in nodes:
        await node.save()

    # Connect nodes to root using entity-centric connect()
    for i, node in enumerate(nodes):
        await root.connect(node, name=f"monitors_{node.name.lower()}")

        # Create some inter-node dependencies
        if i < len(nodes) - 1:
            await node.connect(nodes[i + 1], name="depends_on")


async def demonstrate_event_communication():
    """Demonstrate Walker event communication."""
    print("🔧 Creating alert monitoring graph...")
    await create_alert_graph()

    print("\n🚀 Starting concurrent walkers...")

    # Create different types of walkers
    monitor = MonitoringWalker()
    logger = LoggingWalker()
    analytics = AnalyticsWalker()
    reporter = ReportWalker()

    # Register all walkers with event bus before starting (spawn() does this, but ensure they're all ready)
    from jvspatial.core.events import event_bus

    await asyncio.gather(
        event_bus.register_entity(monitor),
        event_bus.register_entity(logger),
        event_bus.register_entity(analytics),
        event_bus.register_entity(reporter),
    )

    # Start all walkers concurrently (spawn() also registers, but this ensures early registration)
    tasks = [monitor.spawn(), logger.spawn(), analytics.spawn(), reporter.spawn()]

    # Wait for all walkers to complete
    completed_walkers = await asyncio.gather(*tasks)

    print("\n📊 Final Reports:")
    print("=" * 50)

    # Monitor Walker Report
    monitor_report = await monitor.get_report()
    print(f"\n🚨 Monitor Walker ({monitor.id}):")
    print(f"   Alerts sent: {monitor.alerts_sent}")
    alert_count = sum(
        1 for item in monitor_report if isinstance(item, dict) and "alert_sent" in item
    )
    print(f"   Report entries: {len(monitor_report)} (alerts: {alert_count})")

    # Logger Walker Report
    logger_report = await logger.get_report()
    print(f"\n📝 Logger Walker ({logger.id}):")
    print(f"   Events received: {logger.events_received}")
    received_count = sum(
        1
        for item in logger_report
        if isinstance(item, dict) and "received_alert" in item
    )
    print(f"   Report entries: {len(logger_report)} (alerts logged: {received_count})")

    # Analytics Walker Report
    analytics_report = await analytics.get_report()
    print(f"\n📊 Analytics Walker ({analytics.id}):")
    print(f"   Alert breakdown: {analytics.alert_counts}")
    analysis_count = sum(
        1
        for item in analytics_report
        if isinstance(item, dict) and "alert_analysis" in item
    )
    print(f"   Report entries: {len(analytics_report)} (analyses: {analysis_count})")

    # Report Walker Report
    reporter_report = await reporter.get_report()
    print(f"\n📄 Report Walker ({reporter.id}):")
    print(f"   Analytics summaries received: {len(reporter.analytics_received)}")
    print(f"   Report entries: {len(reporter_report)}")

    return {
        "monitor": monitor_report,
        "logger": logger_report,
        "analytics": analytics_report,
        "reporter": reporter_report,
    }


async def demonstrate_event_filtering():
    """Demonstrate event filtering and selective handling."""
    print("\n🔍 Demonstrating Event Filtering:")
    print("-" * 30)

    class CriticalOnlyWalker(Walker):
        """Walker that only handles critical alerts."""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.critical_alerts = 0

        @on_visit(Root)
        async def visit_root(self, here: Root) -> None:
            """Continue traversal from root to connected AlertNodes."""
            connected_nodes = await here.nodes()
            alert_nodes = [n for n in connected_nodes if isinstance(n, AlertNode)]
            if alert_nodes:
                await self.visit(alert_nodes)

        @on_emit("alert_detected")
        async def handle_critical_only(
            self, event_type: str, event_data: Dict[str, Any], source_id: str
        ) -> None:
            """Only process critical alerts."""
            if event_data.get("severity") == "critical":
                self.critical_alerts += 1
                await self.report(
                    {
                        "critical_alert_handled": {
                            "node": event_data.get("name"),
                            "message": event_data.get("message"),
                            "handler": self.id,
                        }
                    }
                )
                print(
                    f"🔥 {self.id}: Handling CRITICAL alert from {event_data.get('name')}"
                )

    # Create walkers
    monitor = MonitoringWalker()
    critical_handler = CriticalOnlyWalker()

    # Register walkers with event bus before starting (ensure they receive events)
    from jvspatial.core.events import event_bus

    await asyncio.gather(
        event_bus.register_entity(monitor),
        event_bus.register_entity(critical_handler),
    )

    # Run them concurrently
    await asyncio.gather(monitor.spawn(), critical_handler.spawn())

    print(f"🔥 Critical alerts handled: {critical_handler.critical_alerts}")
    critical_report = await critical_handler.get_report()
    critical_count = sum(
        1
        for item in critical_report
        if isinstance(item, dict) and "critical_alert_handled" in item
    )
    print(f"🔥 Critical entries in report: {critical_count}")


if __name__ == "__main__":
    print("🚀 Walker Event Communication Demo")
    print("=" * 50)

    async def run_demo():
        # Initialize default context for standalone execution
        db = create_database(db_type="json", base_path="./jvdb")
        ctx = GraphContext(database=db)
        set_default_context(ctx)

        reports = await demonstrate_event_communication()
        await demonstrate_event_filtering()

        print("\n✅ Demo completed successfully!")
        print("\n📝 Key takeaways:")
        print("   • Use walker.emit(event_name, data) to send events to other walkers")
        print("   • Use @on_emit(event_name) to handle specific events")
        print("   • Event handlers can filter and process events selectively")
        print("   • Multiple walkers can run concurrently and communicate")
        print("   • Events enable real-time coordination between walkers")
        print("   • Both walkers and nodes can use @on_emit decorators")
        print(
            "   • Use self.report() to add data to walker reports, not return statements"
        )

        return reports

    asyncio.run(run_demo())
