"""
Demonstrates complex graph traversal with queue management and hooks.
Matches test_walker_traversal.py stress tests.
"""

import os
import random
from typing import List

from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Edge, Node, Walker, on_exit, on_visit
from jvspatial.db.factory import get_database


class City(Node):
    name: str
    population: int
    is_hub: bool = False


class Highway(Edge):
    lanes: int
    distance_km: float


class DeliveryWalker(Walker):
    visited_nodes: List[str] = []
    packages_delivered: int = 0
    total_distance: float = 0.0

    @on_visit(City)
    async def deliver_package(self, here: City):
        """Deliver package to hub cities with 75% probability"""
        if here.is_hub and random.random() < 0.75:
            self.packages_delivered += 1
            print(f"Delivered package to {here.name}")

        self.visited_nodes.append(here.id)

        # Get connected cities via highways
        connections = await here.edges(direction="out")
        highway_connections = [c for c in connections if isinstance(c, Highway)]
        if highway_connections:
            # Get the target nodes from connections
            for conn in highway_connections:
                if conn.source == here.id:
                    target_id = conn.target
                else:
                    target_id = conn.source
                target_node = await Node.get(target_id)
                if target_node and target_node.id not in self.visited_nodes:
                    await self.visit(target_node)
                    break

    @on_visit(Highway)
    async def track_distance(self, here: Highway):
        """Track total distance traveled"""
        self.total_distance += here.distance_km
        print(f"Traveling {here.distance_km}km on {here.id}")

    @on_exit
    async def final_report(self):
        """Generate final traversal report"""
        self.report(
            {
                "delivered": self.packages_delivered,
                "visited": len(self.visited_nodes),
                "distance": round(self.total_distance, 2),
            }
        )


async def complex_traversal():
    """Execute complex traversal with context manager"""
    db_type = os.getenv("JVSPATIAL_DB_TYPE", "json")

    # Get database instance
    database = get_database(db_type=db_type)

    # Create context with database
    ctx = GraphContext(database=database)
    # Create test cities and highways
    metro = await ctx.create(City, name="Metropolis", population=2000000, is_hub=True)
    suburb = await ctx.create(City, name="Suburbville", population=50000)
    await ctx.create(
        Highway, source=metro.id, target=suburb.id, lanes=4, distance_km=50.5
    )

    # Execute traversal
    walker = DeliveryWalker()
    await walker.spawn(start=metro)

    report = walker.get_report()
    print(f"Results: {report}")
    return report


if __name__ == "__main__":
    import asyncio

    asyncio.run(complex_traversal())
