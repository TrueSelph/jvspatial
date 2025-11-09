#!/usr/bin/env python3
"""
Semantic Filtering Example

Demonstrates the semantic filtering approach for the nodes() method with
optimal database-level queries, supporting both simple and complex filtering.
"""

import asyncio
import sys
from pathlib import Path

# Add the current project to the Python path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

from jvspatial.core import Edge, Node
from jvspatial.db import create_database


class City(Node):
    """City node with various properties for filtering."""

    name: str = ""
    population: int = 0
    state: str = ""
    founded_year: int = 0
    climate: str = ""


class Highway(Edge):
    """Highway edge with various properties."""

    name: str = ""
    speed_limit: int = 0
    distance: float = 0.0
    condition: str = "good"
    toll_road: bool = False


class Railroad(Edge):
    """Railroad edge with different properties."""

    name: str = ""
    type: str = "freight"
    max_speed: int = 0
    electrified: bool = False


async def demonstrate_semantic_filtering():
    """Demonstrate semantic filtering with database-level optimization."""

    print("🎯 Semantic Filtering - Database-Optimized Queries")
    print("=" * 60)

    # Create test data
    print("\n📝 Creating test data...")

    # Cities with various properties
    new_york = await City.create(
        name="New York",
        population=8_400_000,
        state="NY",
        founded_year=1624,
        climate="continental",
    )

    boston = await City.create(
        name="Boston",
        population=685_000,
        state="MA",
        founded_year=1630,
        climate="continental",
    )

    philadelphia = await City.create(
        name="Philadelphia",
        population=1_600_000,
        state="PA",
        founded_year=1682,
        climate="continental",
    )

    miami = await City.create(
        name="Miami",
        population=470_000,
        state="FL",
        founded_year=1896,
        climate="tropical",
    )

    # Create connections with various properties
    # High-speed highway
    await new_york.connect(
        boston,
        Highway,
        name="I-95 Northeast",
        speed_limit=70,
        distance=215.0,
        condition="excellent",
        toll_road=True,
    )

    # Medium-speed highway
    await new_york.connect(
        philadelphia,
        Highway,
        name="I-95 Mid-Atlantic",
        speed_limit=65,
        distance=95.0,
        condition="good",
        toll_road=False,
    )

    # Poor condition highway
    await philadelphia.connect(
        miami,
        Highway,
        name="I-95 South",
        speed_limit=70,
        distance=900.0,
        condition="poor",
        toll_road=False,
    )

    # High-speed rail
    await new_york.connect(
        boston,
        Railroad,
        name="Acela Express",
        type="passenger",
        max_speed=150,
        electrified=True,
    )

    # Freight rail
    await new_york.connect(
        philadelphia,
        Railroad,
        name="Northeast Corridor Freight",
        type="freight",
        max_speed=60,
        electrified=False,
    )

    print(
        f"Created {len(await City.find({}))} cities and {len(await Highway.find({})) + len(await Railroad.find({}))} connections"
    )

    # DEMONSTRATE SEMANTIC FILTERING
    print("\n🎯 SEMANTIC FILTERING EXAMPLES")
    print("-" * 50)

    # 1. Simple type filtering
    print("\n1️⃣ Simple Type Filtering:")
    cities = await new_york.nodes(node="City")
    print(f"Connected cities: {[c.name for c in cities]}")

    # 2. Simple property filtering via kwargs
    print("\n2️⃣ Simple Property Filtering (kwargs):")
    ma_connections = await new_york.nodes(state="MA")
    print(f"Massachusetts connections: {[c.name for c in ma_connections]}")

    # Multiple simple filters
    continental_cities = await new_york.nodes(node=["City"], climate="continental")
    print(f"Continental climate cities: {[c.name for c in continental_cities]}")

    # 3. Complex node filtering with MongoDB operators
    print("\n3️⃣ Complex Node Filtering:")
    large_cities = await new_york.nodes(
        node=[{"City": {"context.population": {"$gte": 1_000_000}}}]
    )
    print(f"Large cities (≥1M people): {[c.name for c in large_cities]}")

    # Multiple criteria in node filter
    old_large_cities = await new_york.nodes(
        node=[
            {
                "City": {
                    "context.population": {"$gte": 500_000},
                    "context.founded_year": {"$lt": 1700},
                }
            }
        ]
    )
    print(f"Old large cities (<1700, ≥500K): {[c.name for c in old_large_cities]}")

    # 4. Complex edge filtering
    print("\n4️⃣ Complex Edge Filtering:")
    fast_highways = await new_york.nodes(
        edge=[{"Highway": {"context.speed_limit": {"$gte": 65}}}]
    )
    print(f"Fast highway connections: {[c.name for c in fast_highways]}")

    # Good condition, non-toll roads
    good_free_roads = await new_york.nodes(
        edge=[
            {
                "Highway": {
                    "context.condition": {"$ne": "poor"},
                    "context.toll_road": False,
                }
            }
        ]
    )
    print(f"Good condition, free roads: {[c.name for c in good_free_roads]}")

    # 5. Combined node and edge filtering
    print("\n5️⃣ Combined Node & Edge Filtering:")
    premium_connections = await new_york.nodes(
        direction="out",
        node=[{"City": {"context.population": {"$gte": 500_000}}}],
        edge=[{"Highway": {"context.condition": {"$ne": "poor"}}}],
    )
    print(f"Premium routes to large cities: {[c.name for c in premium_connections]}")

    # 6. Mixed semantic approaches
    print("\n6️⃣ Mixed Semantic Approaches:")
    # Combine complex edge filtering with simple node property filtering
    rail_to_continental = await new_york.nodes(
        edge=[{"Railroad": {"context.type": "passenger"}}],
        climate="continental",  # Simple property via kwargs
    )
    print(
        f"Passenger rail to continental cities: {[c.name for c in rail_to_continental]}"
    )

    # 7. Multi-type filtering
    print("\n7️⃣ Multi-Type Filtering:")
    # Filter by multiple edge types with different criteria
    fast_connections = await new_york.nodes(
        edge=[
            {"Highway": {"context.speed_limit": {"$gte": 65}}},
            {"Railroad": {"context.max_speed": {"$gte": 100}}},
        ]
    )
    print(f"Fast connections (any type): {[c.name for c in fast_connections]}")

    # 8. Direction-specific filtering
    print("\n8️⃣ Direction-Specific Filtering:")
    # Incoming connections with specific criteria
    incoming_large = await boston.nodes(
        direction="in", node=[{"City": {"context.population": {"$gte": 5_000_000}}}]
    )
    print(f"Incoming from large cities (≥5M): {[c.name for c in incoming_large]}")

    # 9. Regex and advanced operators
    print("\n9️⃣ Advanced Operators:")
    interstate_connections = await new_york.nodes(
        edge=[
            {
                "Highway": {
                    "context.name": {"$regex": "^I-.*"},
                    "context.distance": {"$lte": 300},
                }
            }
        ]
    )
    print(f"Interstate highways ≤300 miles: {[c.name for c in interstate_connections]}")

    # States in specific list
    east_coast = await new_york.nodes(
        node=[{"City": {"context.state": {"$in": ["MA", "PA", "FL"]}}}]
    )
    print(f"East coast connections: {[c.name for c in east_coast]}")

    # 10. Performance demonstration
    print("\n🔟 Performance Features:")

    # All these queries are optimized at database level
    print("\n⚡ Database-Level Optimization Features:")
    features = [
        "🗄️  Edge queries with direction, type, and property filtering",
        "🔍 Node queries with type and property filtering",
        "📊 Single-pass filtering reduces database round trips",
        "🎯 Maintains connection order from original edge_ids",
        "💾 Works with MongoDB, JSON, and custom databases",
        "🚀 Supports complex MongoDB-style operators ($gte, $in, $regex, etc.)",
    ]

    for feature in features:
        print(f"  {feature}")

    print("\n✅ Semantic Filtering Demonstration Complete!")
    print("\n🎯 Key Benefits:")
    benefits = [
        "🌟 Semantic simplicity: Use kwargs for simple property filtering",
        "🔧 Complex filtering: Use dict format for advanced MongoDB operators",
        "⚡ Database optimization: Filtering happens at database level",
        "🎯 Flexible syntax: Mix simple and complex approaches as needed",
        "📈 Performance: Reduces memory usage and database round trips",
        "🔄 Walker-ready: Results work directly with walker.visit()",
    ]

    for benefit in benefits:
        print(f"  {benefit}")


if __name__ == "__main__":
    asyncio.run(demonstrate_semantic_filtering())
