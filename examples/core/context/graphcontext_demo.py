"""
GraphContext Dependency Injection Demo

This example demonstrates the new GraphContext pattern for clean database dependency injection
while maintaining the familiar original API. Shows both simple usage (original API) and
advanced usage (explicit GraphContext) patterns.
"""

import asyncio
import tempfile
from typing import List

from jvspatial.core import (
    Edge,
    GraphContext,
    Node,
    Walker,
    get_default_context,
    on_exit,
    on_visit,
)
from jvspatial.db import create_database


# Entity definitions
class City(Node):
    """A city node with geographic data."""

    name: str
    population: int = 0
    latitude: float = 0.0
    longitude: float = 0.0


class Highway(Edge):
    """Highway connection between cities."""

    distance_km: float = 0.0
    lanes: int = 4


class Tourist(Walker):
    """Walker that visits cities and tracks distances."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cities_visited = []

    @on_visit(City)
    async def visit_city(self, here: City):
        """Visit a city and record the visit."""
        self.cities_visited.append(here.name)
        await self.report({"city_visited": here.name})
        print(f"🏛️  Visiting {here.name} (population: {here.population:,})")

    @on_exit
    async def trip_summary(self):
        """Provide a trip summary."""
        print(f"🎒 Trip complete! Visited {len(self.cities_visited)} cities")
        await self.report(
            {
                "trip_summary": {
                    "total_cities": len(self.cities_visited),
                    "cities": self.cities_visited,
                }
            }
        )


async def demonstrate_original_api():
    """
    Pattern 1: Original API (Simplest)

    Uses the default GraphContext automatically - no changes needed to existing code!
    This is how users have always used the library and continues to work exactly the same.
    """
    print("=" * 50)
    print("PATTERN 1: ORIGINAL API (No Changes Needed)")
    print("=" * 50)

    # All original syntax works exactly the same!
    chicago = await City.create(
        name="Chicago", population=2700000, latitude=41.88, longitude=-87.63
    )
    milwaukee = await City.create(
        name="Milwaukee", population=590000, latitude=43.04, longitude=-87.91
    )

    # Connect cities with highway
    highway = await Highway.create(
        left=chicago, right=milwaukee, distance_km=118, lanes=6
    )

    print(f"✅ Created {chicago.name} and {milwaukee.name}")
    print(f"✅ Connected with highway: {highway.distance_km}km, {highway.lanes} lanes")

    # Original walker usage - unchanged
    tourist = Tourist()
    await tourist.spawn(chicago)

    return [chicago, milwaukee, highway]


async def demonstrate_explicit_context():
    """
    Pattern 2: Explicit GraphContext

    For advanced users who want explicit control over database connections.
    Great for testing, multi-database scenarios, or when you need isolation.
    """
    print("\n" + "=" * 50)
    print("PATTERN 2: EXPLICIT GRAPHCONTEXT")
    print("=" * 50)

    # Create a specific database instance
    temp_db_path = tempfile.mkdtemp()
    custom_db = create_database(db_type="json", base_path=temp_db_path)

    # Create GraphContext with custom database
    ctx = GraphContext(database=custom_db)

    print(f"📁 Using custom database at: {temp_db_path}")

    # Use context for all operations
    seattle = await ctx.create_node(
        City, name="Seattle", population=750000, latitude=47.61, longitude=-122.33
    )
    portland = await ctx.create_node(
        City, name="Portland", population=650000, latitude=45.52, longitude=-122.67
    )

    # Create highway connection
    highway = await ctx.create_edge(
        Highway, left=seattle, right=portland, distance_km=278, lanes=4
    )

    print(f"✅ Created {seattle.name} and {portland.name} in custom database")
    print(f"✅ Connected with highway: {highway.distance_km}km")

    # Walkers can use entities from any context
    tourist = Tourist()
    await tourist.spawn(seattle)

    return ctx, [seattle, portland, highway]


async def demonstrate_multiple_contexts():
    """
    Pattern 3: Multiple Database Contexts

    Shows how to work with multiple databases simultaneously - great for
    separating concerns (e.g., main data vs. analytics/logging).
    """
    print("\n" + "=" * 50)
    print("PATTERN 3: MULTIPLE DATABASE CONTEXTS")
    print("=" * 50)

    # Main database for application data
    main_db = create_database(db_type="json", base_path=tempfile.mkdtemp())
    main_ctx = GraphContext(database=main_db)

    # Analytics database for logging/metrics
    analytics_db = create_database(db_type="json", base_path=tempfile.mkdtemp())
    analytics_ctx = GraphContext(database=analytics_db)

    print("📊 Created separate contexts for main data and analytics")

    # Create main application data
    boston = await main_ctx.create_node(City, name="Boston", population=685000)
    new_york = await main_ctx.create_node(City, name="New York", population=8400000)

    # Create analytics/logging data
    class LogEntry(Node):
        action: str
        timestamp: str = "2024-01-17T10:00:00Z"
        details: str = ""

    log_entry = await analytics_ctx.create_node(
        LogEntry,
        action="cities_created",
        details=f"Created {boston.name} and {new_york.name}",
    )

    print(f"🏙️  Main DB: Created {boston.name} and {new_york.name}")
    print(f"📝 Analytics DB: Logged action '{log_entry.action}'")

    # Both databases work independently
    main_cities = [
        n
        for n in await main_ctx.database.find("node", {})
        if n.get("name") in ["Boston", "New York"]
    ]
    analytics_logs = await analytics_ctx.database.find("node", {})

    print(f"📈 Main database has {len(main_cities)} cities")
    print(f"📊 Analytics database has {len(analytics_logs)} log entries")


async def demonstrate_testing_pattern():
    """
    Pattern 4: Testing with GraphContext

    Shows how GraphContext makes testing much easier by allowing
    injection of mock databases or isolated test databases.
    """
    print("\n" + "=" * 50)
    print("PATTERN 4: TESTING PATTERN")
    print("=" * 50)

    # Create isolated test database
    test_db_path = tempfile.mkdtemp()
    test_db = create_database(db_type="json", base_path=test_db_path)
    test_ctx = GraphContext(database=test_db)

    print(f"🧪 Created isolated test database at: {test_db_path}")

    # Test operations in isolation
    test_city = await test_ctx.create_node(City, name="Test City", population=100000)

    # Verify test isolation
    retrieved = await test_ctx.get_node(City, test_city.id)
    assert retrieved is not None
    assert retrieved.name == "Test City"

    print("✅ Test operations work in isolation")
    print("✅ No interference with other databases")

    # Demonstrate original API still works even with custom context
    # (entities remember their context)
    test_city.population = 150000  # Modify the entity
    await test_city.save()  # Original API - uses the entity's context automatically

    print("✅ Original API (entity.save()) works with custom contexts")


async def demonstrate_backwards_compatibility():
    """
    Pattern 5: 100% Backwards Compatibility

    Shows that ALL existing code continues to work without modification.
    """
    print("\n" + "=" * 50)
    print("PATTERN 5: 100% BACKWARDS COMPATIBILITY")
    print("=" * 50)

    print("🔄 All existing user code works without changes:")

    # All the classic patterns still work:

    # 1. Create nodes and edges
    node1 = await City.create(name="Legacy City 1", population=500000)
    node2 = await City.create(name="Legacy City 2", population=600000)

    # 2. Connect them
    connection = await node1.connect(node2, Highway, distance_km=200)

    # 3. Retrieve by ID
    retrieved_node = await City.get(node1.id)
    retrieved_edge = await Highway.get(connection.id)

    # 4. Modify and save
    retrieved_node.population = 550000
    await retrieved_node.save()

    # 5. Walker traversal
    class LegacyWalker(Walker):
        @on_visit(City)
        async def process_city(self, here):
            print(f"  Processing {here.name} with {here.population:,} people")

    walker = LegacyWalker()
    await walker.spawn(node1)

    print("✅ All legacy patterns work perfectly!")
    print("✅ No breaking changes to existing code")


async def main():
    """
    GraphContext Dependency Injection Demo

    Shows the evolution from scattered database selection to clean dependency injection
    while maintaining perfect backwards compatibility.
    """
    print("🚀 GraphContext Dependency Injection Demo")
    print("📋 Eliminates scattered database selection while preserving original API\n")

    # Show the progression from simple to advanced
    await demonstrate_original_api()
    await demonstrate_explicit_context()
    await demonstrate_multiple_contexts()
    await demonstrate_testing_pattern()
    await demonstrate_backwards_compatibility()

    print("\n" + "=" * 50)
    print("🎉 DEMO COMPLETE")
    print("=" * 50)
    print("Key Benefits Demonstrated:")
    print("✅ Clean dependency injection with GraphContext")
    print("✅ No more scattered database selection")
    print("✅ Easy testing with database isolation")
    print("✅ Multiple database support")
    print("✅ 100% backwards compatibility")
    print("✅ Original API unchanged for existing users")


if __name__ == "__main__":
    asyncio.run(main())
