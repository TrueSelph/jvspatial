"""
Object-spatial ORM demonstration for jvspatial core module.

This example shows the semantic simplicity, database optimization,
and elegant design of the jvspatial object-spatial ORM.
"""

import asyncio

from pydantic import Field

from jvspatial.core import Edge, Node, Walker, on_visit


class City(Node):
    """Example city node."""

    name: str = Field(default="")
    population: int = Field(default=0)


class Highway(Edge):
    """Example highway edge."""

    distance: float = Field(default=0.0)
    lanes: int = Field(default=2)


class TravelWalker(Walker):
    """Walker that travels between cities."""

    cities_visited: list = Field(default_factory=list)
    total_distance: float = Field(default=0.0)

    @on_visit(City)
    async def visit_city(self, here: City):
        """Visit a city and continue journey."""
        print(f"🚶 Visiting {here.name} (pop: {here.population:,})")
        self.cities_visited.append(here.name)

        # Visit unvisited neighbors
        neighbors = await here.neighbors(limit=2)
        unvisited = [n for n in neighbors if n.name not in self.cities_visited]
        if unvisited:
            await self.visit(unvisited)

    @on_visit(Highway)
    async def travel_highway(self, highway: Highway):
        """Travel along a highway."""
        print(f"   🛣️  Traveling {highway.distance} miles")
        self.total_distance += highway.distance


async def demonstrate_orm():
    """Demonstrate the jvspatial object-spatial ORM features."""

    print("🌟 jvspatial Object-Spatial ORM Demonstration\n")

    # 1. Semantic Simplicity - Creating nodes is straightforward
    print("1️⃣ Creating nodes with semantic simplicity:")
    new_york = City(name="New York", population=8000000)
    los_angeles = City(name="Los Angeles", population=4000000)
    chicago = City(name="Chicago", population=2700000)

    print(f"   ✅ Created {new_york.name} (pop: {new_york.population:,})")
    print(f"   ✅ Created {los_angeles.name} (pop: {los_angeles.population:,})")
    print(f"   ✅ Created {chicago.name} (pop: {chicago.population:,})")

    # 2. Simple Connection Interface
    print("\n2️⃣ Connecting nodes with elegant syntax:")
    highway1 = await new_york.connect(chicago, Highway, distance=790.0, lanes=4)
    highway2 = await chicago.connect(los_angeles, Highway, distance=2015.0, lanes=6)
    highway3 = await new_york.connect(los_angeles, Highway, distance=2445.0, lanes=4)

    print(
        f"   ✅ Connected {new_york.name} ↔ {chicago.name} ({highway1.distance} miles)"
    )
    print(
        f"   ✅ Connected {chicago.name} ↔ {los_angeles.name} ({highway2.distance} miles)"
    )
    print(
        f"   ✅ Connected {new_york.name} ↔ {los_angeles.name} ({highway3.distance} miles)"
    )

    # 3. Connection Information
    print("\n3️⃣ Connection information:")
    print(f"   📊 {new_york.name} has {new_york.connection_count} connections")
    print(f"   📊 {chicago.name} has {chicago.connection_count} connections")
    print(f"   📊 {los_angeles.name} has {los_angeles.connection_count} connections")

    # 4. Traversal with preserved ordering
    print("\n4️⃣ Traversing connections (preserves add order):")
    ny_neighbors = await new_york.neighbors()
    print(f"   🗺️  {new_york.name}'s neighbors:")
    for i, neighbor in enumerate(ny_neighbors, 1):
        print(f"      {i}. {neighbor.name} (pop: {neighbor.population:,})")

    # 5. Directional traversal
    print("\n5️⃣ Directional traversal:")
    outgoing = await chicago.outgoing()
    incoming = await chicago.incoming()
    print(f"   ➡️  Outgoing from {chicago.name}: {[city.name for city in outgoing]}")
    print(f"   ⬅️  Incoming to {chicago.name}: {[city.name for city in incoming]}")

    # 6. Connection checking
    print("\n6️⃣ Connection checking:")
    is_connected = await new_york.is_connected_to(chicago)
    print(f"   🔗 {new_york.name} connected to {chicago.name}: {is_connected}")

    # 7. Disconnection
    print("\n7️⃣ Disconnection:")
    disconnected = await new_york.disconnect(los_angeles, Highway)
    print(f"   ✂️  Disconnected {new_york.name} from {los_angeles.name}: {disconnected}")
    print(f"   📊 {new_york.name} now has {new_york.connection_count} connections")

    # 8. Database query optimization (find nodes by properties)
    print("\n8️⃣ Database-optimized queries:")
    large_cities = await City.find_by(population={"$gt": 5000000})
    print(f"   🏙️  Large cities (>5M pop): {[city.name for city in large_cities]}")

    # 9. Creating connected nodes in one operation
    print("\n9️⃣ Create and connect in one operation:")
    denver = await City.create_and_connect(
        chicago, Highway, name="Denver", population=715000, distance=920.0, lanes=4
    )
    print(f"   ✅ Created and connected {denver.name} to {chicago.name}")

    print(
        f"\n🎯 Final network: {chicago.name} now has {chicago.connection_count} connections"
    )

    # 10. Walker traversal
    print("\n🔟 Walker-based traversal:")
    traveler = TravelWalker()
    await traveler.spawn(start=new_york)

    print(f"   🚶 Walker visited: {traveler.cities_visited}")
    print(f"   📏 Total distance: {traveler.total_distance} miles")

    print("\n✨ Object-spatial ORM demonstration complete!")
    print("\n📋 Architecture Components Used:")
    print("   • Objects: Simple data storage units")
    print("   • Nodes: Connected objects that can be visited")
    print("   • Edges: Connections between nodes")
    print("   • Walkers: Traverse nodes along edges")


if __name__ == "__main__":
    asyncio.run(demonstrate_orm())
