#!/usr/bin/env python3
"""
Walker Reporting Demo

This example demonstrates the new Walker reporting system that allows
walkers to aggregate and collect data during traversal using the report() method.
"""

import asyncio
from typing import Any, Dict, List

from jvspatial.core import Edge, GraphContext, Node, Root, Walker, on_exit, on_visit
from jvspatial.core.context import set_default_context
from jvspatial.db import create_database


class DataNode(Node):
    """A node that contains some data to be collected."""

    name: str = ""
    value: int = 0
    category: str = "default"


class CollectorWalker(Walker):
    """A walker that collects data from nodes and generates reports."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.total_collected = 0
        self.categories_seen = set()

    @on_visit(Root)
    async def visit_root(self, here: Root) -> None:
        """Continue traversal from root to connected DataNodes."""
        connected_nodes = await here.nodes()
        data_nodes = [n for n in connected_nodes if isinstance(n, DataNode)]
        if data_nodes:
            await self.visit(data_nodes)

    @on_visit(DataNode)
    async def collect_data(self, here: DataNode) -> None:
        """Collect data from DataNode instances."""
        # Skip if already visited (check trail)
        if self.is_visited(here):
            return

        # Report individual node data
        report_data = await self.get_report()
        await self.report(
            {
                "node_id": here.id,
                "name": here.name,
                "value": here.value,
                "category": here.category,
                "collection_order": len(report_data) + 1,
            }
        )

        # Update internal tracking
        self.total_collected += here.value
        self.categories_seen.add(here.category)

        print(
            f"Collected: {here.name} (value: {here.value}, category: {here.category})"
        )

        # Continue traversal to connected nodes (only unvisited ones, check trail)
        connected_nodes = await here.nodes()
        data_neighbors = [
            n
            for n in connected_nodes
            if isinstance(n, DataNode) and not self.is_visited(n)
        ]
        if data_neighbors:
            await self.visit(data_neighbors)

    @on_exit
    async def generate_summary(self) -> None:
        """Generate a summary report using the traversal trail."""
        # Calculate unique nodes and values from report items
        report_data = await self.get_report()
        unique_values = {}
        for item in report_data:
            if isinstance(item, dict) and "node_id" in item and "value" in item:
                node_id = item.get("node_id")
                if node_id and node_id not in unique_values:
                    unique_values[node_id] = item.get("value", 0)

        unique_count = len(unique_values)
        unique_total_value = sum(unique_values.values())
        avg_value = unique_total_value / unique_count if unique_count > 0 else 0

        # Report summary
        await self.report(
            {
                "summary": {
                    "total_nodes_visited": self.get_trail_length(),
                    "unique_nodes_processed": unique_count,
                    "trail_length": self.get_trail_length(),
                    "trail": self.get_trail(),
                    "total_value_collected": unique_total_value,
                    "average_value": round(avg_value, 2),
                    "categories_found": list(self.categories_seen),
                    "category_count": len(self.categories_seen),
                }
            }
        )


class AnalyticsWalker(Walker):
    """A walker that performs analytics on collected data."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.value_ranges = {"low": [], "medium": [], "high": []}

    @on_visit(Root)
    async def visit_root(self, here: Root) -> None:
        """Continue traversal from root to connected DataNodes."""
        connected_nodes = await here.nodes()
        data_nodes = [n for n in connected_nodes if isinstance(n, DataNode)]
        if data_nodes:
            await self.visit(data_nodes)

    @on_visit(DataNode)
    async def analyze_data(self, here: DataNode) -> None:
        """Analyze data and categorize by value ranges."""
        # Skip if already visited (check trail)
        if self.is_visited(here):
            return

        if here.value < 10:
            range_category = "low"
        elif here.value < 50:
            range_category = "medium"
        else:
            range_category = "high"

        self.value_ranges[range_category].append(
            {"node_id": here.id, "name": here.name, "value": here.value}
        )

        # Report the analysis
        await self.report(
            {
                "analysis": {
                    "node_id": here.id,
                    "name": here.name,
                    "value": here.value,
                    "value_range": range_category,
                    "percentile": self._calculate_percentile(here.value),
                }
            }
        )

        # Continue traversal to connected nodes (only unvisited ones, check trail)
        connected_nodes = await here.nodes()
        data_neighbors = [
            n
            for n in connected_nodes
            if isinstance(n, DataNode) and not self.is_visited(n)
        ]
        if data_neighbors:
            await self.visit(data_neighbors)

    def _calculate_percentile(self, value: int) -> str:
        """Simple percentile calculation."""
        if value < 5:
            return "bottom_10"
        elif value < 20:
            return "bottom_50"
        elif value < 60:
            return "top_50"
        else:
            return "top_10"

    @on_exit
    async def generate_analytics_summary(self) -> None:
        """Generate analytics summary."""
        await self.report(
            {
                "analytics_summary": {
                    "value_distribution": {
                        "low_values": len(self.value_ranges["low"]),
                        "medium_values": len(self.value_ranges["medium"]),
                        "high_values": len(self.value_ranges["high"]),
                    },
                    "recommendations": self._generate_recommendations(),
                }
            }
        )

    def _generate_recommendations(self) -> List[str]:
        """Generate simple recommendations based on data distribution."""
        recommendations = []

        if len(self.value_ranges["high"]) > len(self.value_ranges["low"]) + len(
            self.value_ranges["medium"]
        ):
            recommendations.append("High concentration of high-value nodes detected")

        if len(self.value_ranges["low"]) > 5:
            recommendations.append("Consider optimizing low-value nodes")

        if not recommendations:
            recommendations.append("Data distribution appears balanced")

        return recommendations


async def create_sample_graph() -> None:
    """Create a sample graph with data nodes."""
    root = await Root.get()  # type: ignore[call-arg]
    if root is None:
        raise RuntimeError("Could not get root node")

    # Create data nodes with various values and categories
    nodes = [
        DataNode(name="Alpha", value=15, category="processing"),
        DataNode(name="Beta", value=42, category="storage"),
        DataNode(name="Gamma", value=8, category="processing"),
        DataNode(name="Delta", value=67, category="compute"),
        DataNode(name="Epsilon", value=23, category="storage"),
        DataNode(name="Zeta", value=3, category="processing"),
        DataNode(name="Eta", value=91, category="compute"),
        DataNode(name="Theta", value=34, category="storage"),
    ]

    # Save all nodes
    for node in nodes:
        await node.save()

    # Connect nodes to root and create a traversal path using entity-centric API
    for i, node in enumerate(nodes):
        await root.connect(node, name=f"connects_to_{node.name.lower()}")

        # Create some inter-node connections
        if i < len(nodes) - 1:
            await node.connect(nodes[i + 1], name="next_in_sequence")


async def demonstrate_reporting():
    """Demonstrate the Walker reporting system."""
    print("🔧 Creating sample graph...")
    await create_sample_graph()

    print("\n📊 Running data collection walker...")
    collector = CollectorWalker()
    await collector.spawn()

    # Get the complete report
    collector_report = await collector.get_report()
    print(f"\n📋 Collector Report:")
    print(f"   Total items in report: {len(collector_report)}")

    # Show trail insights
    collector_trail_ids = collector.get_trail_path()
    print(f"   Trail length: {collector.get_trail_length()}")
    print(f"   Trail (node ids): {collector_trail_ids}")

    # Show individual data points (unique nodes only)
    seen_node_ids = set()
    unique_items = []
    for item in collector_report:
        if isinstance(item, dict) and "node_id" in item:
            node_id = item.get("node_id")
            if node_id and node_id not in seen_node_ids:
                seen_node_ids.add(node_id)
                unique_items.append(item)
                print(
                    f"   • {item.get('name', 'Unknown')}: {item.get('value', 0)} ({item.get('category', 'unknown')})"
                )

    # Calculate summary from unique nodes
    total_unique_value = sum(item.get("value", 0) for item in unique_items)
    unique_count = len(unique_items)
    categories = set(
        item.get("category", "") for item in unique_items if item.get("category")
    )

    # Check for summary in report (from @on_exit hook)
    summary_data = None
    for item in collector_report:
        if isinstance(item, dict) and "summary" in item:
            summary_data = item["summary"]
            break

    if summary_data:
        print(f"\n📈 Summary:")
        print(
            f"   • Total trail steps: {summary_data.get('total_nodes_visited', collector.get_trail_length())}"
        )
        print(
            f"   • Unique nodes processed: {summary_data.get('unique_nodes_processed', unique_count)}"
        )
        print(
            f"   • Total value: {summary_data.get('total_value_collected', total_unique_value)}"
        )
        print(
            f"   • Average value: {summary_data.get('average_value', total_unique_value / unique_count if unique_count > 0 else 0.0):.2f}"
        )
        print(
            f"   • Categories: {', '.join(sorted(summary_data.get('categories_found', categories)))}"
        )
    else:
        print(f"\n📈 Summary:")
        print(f"   • Total trail steps: {collector.get_trail_length()}")
        print(f"   • Unique nodes processed: {unique_count}")
        print(f"   • Total value: {total_unique_value}")
        print(
            f"   • Average value: {total_unique_value / unique_count if unique_count > 0 else 0.0:.2f}"
        )
        print(f"   • Categories: {', '.join(sorted(categories))}")

    print("\n🔍 Running analytics walker...")
    analytics = AnalyticsWalker()
    await analytics.spawn()

    # Get the analytics report
    analytics_report = await analytics.get_report()
    print(f"\n📊 Analytics Report:")
    print(f"   Total analyses: {len(analytics_report)}")

    # Show trail insights
    print(f"   Trail length: {analytics.get_trail_length()}")
    print(f"   Trail (node ids): {analytics.get_trail()}")

    # Show analytics summary
    for item in analytics_report:
        if isinstance(item, dict) and "analytics_summary" in item:
            summary = item["analytics_summary"]
            dist = summary["value_distribution"]
            print(f"\n📊 Value Distribution:")
            print(f"   • Low values (< 10): {dist['low_values']}")
            print(f"   • Medium values (10-49): {dist['medium_values']}")
            print(f"   • High values (≥ 50): {dist['high_values']}")
            print(f"\n💡 Recommendations:")
            for rec in summary["recommendations"]:
                print(f"   • {rec}")


async def demonstrate_report_access():
    """Demonstrate different ways to access report data."""
    print("\n🔍 Demonstrating report access patterns...")

    walker = CollectorWalker()
    result_walker = await walker.spawn()  # spawn returns the walker instance

    # Access report through the returned walker
    report = await result_walker.get_report()
    print(f"Report accessed from returned walker: {len(report)} items")

    # Access report through the original walker reference (same object)
    same_report = await walker.get_report()
    print(f"Report accessed from original walker: {len(same_report)} items")

    # Demonstrate that they're the same
    print(f"Reports are identical: {report == same_report}")


if __name__ == "__main__":
    print("🚀 Walker Reporting System Demo")
    print("=" * 50)

    async def run_demo():
        # Initialize default context for standalone execution
        db = create_database(db_type="json", base_path="./jvdb")
        ctx = GraphContext(database=db)
        set_default_context(ctx)

        await demonstrate_reporting()
        await demonstrate_report_access()

        print("\n✅ Demo completed successfully!")
        print("\n📝 Key takeaways:")
        print("   • Use walker.report(data) to add any data to the walker's report")
        print("   • Use walker.get_report() to retrieve all collected data")
        print("   • spawn() returns the walker instance for immediate report access")
        print("   • Reports can contain any serializable data")
        print("   • Use @on_exit hooks to generate summaries and final reports")

    asyncio.run(run_demo())
