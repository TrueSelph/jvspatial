#!/usr/bin/env python3
"""
Enhanced Nodes Filtering Example

Demonstrates the enhanced nodes() method with MongoDB-style comparison operators
for sophisticated edge property filtering during graph traversal.
"""

import asyncio
import sys
from pathlib import Path

# Add the current project to the Python path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

from jvspatial.core import Edge, Node
from jvspatial.db import create_database


class City(Node):
    """City node with population and other attributes."""

    name: str = ""
    population: int = 0
    state: str = ""
    founded_year: int = 0


class Highway(Edge):
    """Highway edge with various properties for filtering."""

    name: str = ""
    speed_limit: int = 0
    distance: float = 0.0
    toll_road: bool = False
    surface: str = "asphalt"
    condition: str = "good"
    lanes: int = 2


class Railroad(Edge):
    """Railroad edge with different properties."""

    name: str = ""
    type: str = "freight"  # freight, passenger, mixed
    max_speed: int = 0
    electrified: bool = False


async def demonstrate_enhanced_filtering():
    """Demonstrate enhanced filtering with MongoDB-style operators."""

    print("🚀 Enhanced Nodes Filtering - MongoDB-Style Operators")
    print("=" * 60)

    # Create cities
    print("\n📝 Creating cities...")
    new_york = await City.create(
        name="New York", population=8_400_000, state="NY", founded_year=1624
    )
    boston = await City.create(
        name="Boston", population=685_000, state="MA", founded_year=1630
    )
    philadelphia = await City.create(
        name="Philadelphia", population=1_600_000, state="PA", founded_year=1682
    )
    washington_dc = await City.create(
        name="Washington DC", population=700_000, state="DC", founded_year=1790
    )

    cities = await City.find({})
    print(f"Created {len(cities)} cities")

    # Create highways with various properties
    print("\n🛣️  Creating highways...")

    # I-95: High-speed, toll road
    i95_ny_boston = await new_york.connect(
        boston,
        Highway,
        name="Interstate 95",
        speed_limit=65,
        distance=215.0,
        toll_road=True,
        surface="concrete",
        condition="excellent",
        lanes=4,
    )

    # I-95 continuation: Different properties
    i95_boston_philadelphia = await boston.connect(
        philadelphia,
        Highway,
        name="Interstate 95",
        speed_limit=70,
        distance=310.0,
        toll_road=False,
        surface="asphalt",
        condition="good",
        lanes=3,
    )

    # US-1: Slower, local road
    us1_ny_philadelphia = await new_york.connect(
        philadelphia,
        Highway,
        name="US Route 1",
        speed_limit=45,
        distance=95.0,
        toll_road=False,
        surface="asphalt",
        condition="fair",
        lanes=2,
    )

    # I-495: Beltway around DC
    i495_philadelphia_dc = await philadelphia.connect(
        washington_dc,
        Highway,
        name="Interstate 495",
        speed_limit=55,
        distance=140.0,
        toll_road=True,
        surface="concrete",
        condition="poor",
        lanes=6,
    )

    # Railroad connection
    amtrak_ny_boston = await new_york.connect(
        boston,
        Railroad,
        name="Northeast Corridor",
        type="passenger",
        max_speed=150,
        electrified=True,
    )

    print(
        f"Created {len(await Highway.find({}))} highways and {len(await Railroad.find({}))} railroads"
    )

    # DEMONSTRATE ENHANCED FILTERING
    print("\n🔍 ENHANCED FILTERING EXAMPLES")
    print("-" * 40)

    # 1. Simple equality filtering
    print("\n1️⃣ Simple Equality Filtering:")
    toll_roads = await new_york.nodes(edge=[Highway], toll_road=True)
    print(f"Cities connected by toll roads: {[c.name for c in toll_roads]}")

    # 2. Comparison operators
    print("\n2️⃣ Comparison Operators:")

    # Speed limit >= 60
    fast_routes = await new_york.nodes(edge=[Highway], speed_limit={"$gte": 60})
    print(f"Fast routes (≥60 mph): {[c.name for c in fast_routes]}")

    # Distance < 200 miles
    short_routes = await new_york.nodes(edge=[Highway], distance={"$lt": 200.0})
    print(f"Short routes (<200 mi): {[c.name for c in short_routes]}")

    # Multiple comparisons
    optimal_routes = await new_york.nodes(
        edge=[Highway],
        speed_limit={"$gte": 60},
        distance={"$lte": 250.0},
        toll_road={"$ne": True},  # Not a toll road
    )
    print(
        f"Optimal routes (fast, medium distance, no tolls): {[c.name for c in optimal_routes]}"
    )

    # 3. Set operations ($in, $nin)
    print("\n3️⃣ Set Operations:")

    # Surface type in list
    quality_surfaces = await new_york.nodes(
        edge=[Highway], surface={"$in": ["concrete", "asphalt"]}
    )
    print(f"Quality surface roads: {[c.name for c in quality_surfaces]}")

    # Exclude poor conditions
    good_condition = await new_york.nodes(
        edge=[Highway], condition={"$nin": ["poor", "closed"]}
    )
    print(f"Good condition roads: {[c.name for c in good_condition]}")

    # 4. Regular expression matching
    print("\n4️⃣ Regular Expression Matching:")

    # Interstate highways only
    interstates = await new_york.nodes(edge=[Highway], name={"$regex": "^Interstate.*"})
    print(f"Interstate highways: {[c.name for c in interstates]}")

    # Routes with numbers (I-95, US-1, etc.)
    numbered_routes = await new_york.nodes(edge=[Highway], name={"$regex": ".*\\d+.*"})
    print(f"Numbered routes: {[c.name for c in numbered_routes]}")

    # 5. Complex multi-criteria filtering
    print("\n5️⃣ Complex Multi-Criteria Filtering:")

    # Premium routes: Interstate, fast, good condition, concrete
    premium_routes = await new_york.nodes(
        edge=[Highway],
        name={"$regex": "^Interstate.*"},
        speed_limit={"$gte": 60},
        surface="concrete",
        condition={"$in": ["good", "excellent"]},
        lanes={"$gte": 3},
    )
    print(f"Premium interstate routes: {[c.name for c in premium_routes]}")

    # 6. Mixed edge types with filtering
    print("\n6️⃣ Mixed Edge Types:")

    # Any high-speed connection (highway or rail)
    high_speed = await new_york.nodes(
        node=["City"],  # Only cities
        speed_limit={"$gte": 60},  # For highways
        max_speed={"$gte": 100},  # For railroads (this will be ignored for highways)
    )
    print(f"High-speed connections: {[c.name for c in high_speed]}")

    # 7. Direction-specific filtering
    print("\n7️⃣ Direction-Specific Filtering:")

    # From Boston, find incoming routes with specific criteria
    incoming_to_boston = await boston.nodes(
        direction="in", edge=[Highway], distance={"$gte": 200.0}
    )
    print(f"Long routes into Boston: {[c.name for c in incoming_to_boston]}")

    # 8. Performance comparison
    print("\n8️⃣ Performance Features:")

    # Multiple regex patterns (will use pre-compiled patterns internally)
    interstate_routes = []
    for city in [new_york, boston, philadelphia]:
        routes = await city.nodes(
            edge=[Highway],
            name={"$regex": "^Interstate.*"},
            condition={"$regex": "^(good|excellent)$"},
        )
        interstate_routes.extend([(city.name, r.name) for r in routes])

    print(f"All interstate routes from major cities: {interstate_routes}")

    print("\n✅ Enhanced Filtering Demonstration Complete!")
    print("\n🎯 Supported MongoDB-Style Operators:")
    operators = [
        "$eq (equal)",
        "$ne (not equal)",
        "$gt (greater than)",
        "$gte (greater than or equal)",
        "$lt (less than)",
        "$lte (less than or equal)",
        "$in (in list)",
        "$nin (not in list)",
        "$regex (pattern match)",
        "$exists (field exists)",
    ]
    for op in operators:
        print(f"  • {op}")


if __name__ == "__main__":
    asyncio.run(demonstrate_enhanced_filtering())
