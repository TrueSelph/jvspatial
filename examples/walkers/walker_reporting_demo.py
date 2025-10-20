#!/usr/bin/env python3
"""
Walker Reporting Demo

This example demonstrates the new Walker reporting system that allows
walkers to aggregate and collect data during traversal using the report() method.
"""

import asyncio
from typing import Any, Dict, List

from jvspatial.core import Edge, GraphContext, Node, Root, Walker, on_exit, on_visit


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

    @on_visit(DataNode)
    async def collect_data(self, here: DataNode) -> None:
        """Collect data from DataNode instances."""
        # Report individual node data
        self.report(
            {
                "node_id": here.id,
                "name": here.name,
                "value": here.value,
                "category": here.category,
                "collection_order": len(self.get_report()) + 1,
            }
        )

        # Update internal tracking
        self.total_collected += here.value
        self.categories_seen.add(here.category)

        print(
            f"Collected: {here.name} (value: {here.value}, category: {here.category})"
        )

    @on_exit
    async def generate_summary(self) -> None:
        """Generate a summary report when traversal is complete."""
        report_data = self.get_report()

        # Calculate summary statistics
        total_nodes = len(report_data)
        avg_value = self.total_collected / total_nodes if total_nodes > 0 else 0

        # Report summary
        self.report(
            {
                "summary": {
                    "total_nodes_visited": total_nodes,
                    "total_value_collected": self.total_collected,
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

    @on_visit(DataNode)
    async def analyze_data(self, here: DataNode) -> None:
        """Analyze data and categorize by value ranges."""
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
        self.report(
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
        self.report(
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

    # Connect nodes to root and create a traversal path
    for i, node in enumerate(nodes):
        edge = Edge(
            source_id=root.id,
            target_id=node.id,
            name=f"connects_to_{node.name.lower()}",
        )
        await edge.save()

        # Create some inter-node connections
        if i < len(nodes) - 1:
            inter_edge = Edge(
                source_id=node.id,
                target_id=nodes[i + 1].id,
                name=f"next_in_sequence",
            )
            await inter_edge.save()


async def demonstrate_reporting():
    """Demonstrate the Walker reporting system."""
    print("🔧 Creating sample graph...")
    await create_sample_graph()

    print("\n📊 Running data collection walker...")
    collector = CollectorWalker()
    await collector.spawn()

    # Get the complete report
    collector_report = collector.get_report()
    print(f"\n📋 Collector Report:")
    print(f"   Total items in report: {len(collector_report)}")

    # Show individual data points
    for item in collector_report:
        if isinstance(item, dict) and "name" in item:  # Individual node data
            print(f"   • {item['name']}: {item['value']} ({item['category']})")
        elif isinstance(item, dict) and "summary" in item:  # Summary data
            summary = item["summary"]
            print(f"\n📈 Summary:")
            print(f"   • Nodes visited: {summary['total_nodes_visited']}")
            print(f"   • Total value: {summary['total_value_collected']}")
            print(f"   • Average value: {summary['average_value']}")
            print(f"   • Categories: {', '.join(summary['categories_found'])}")

    print("\n🔍 Running analytics walker...")
    analytics = AnalyticsWalker()
    await analytics.spawn()

    # Get the analytics report
    analytics_report = analytics.get_report()
    print(f"\n📊 Analytics Report:")
    print(f"   Total analyses: {len(analytics_report)}")

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
    report = result_walker.get_report()
    print(f"Report accessed from returned walker: {len(report)} items")

    # Access report through the original walker reference (same object)
    same_report = walker.get_report()
    print(f"Report accessed from original walker: {len(same_report)} items")

    # Demonstrate that they're the same
    print(f"Reports are identical: {report == same_report}")


if __name__ == "__main__":
    print("🚀 Walker Reporting System Demo")
    print("=" * 50)

    async def run_demo():
        # No architecture setup needed - use default

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
