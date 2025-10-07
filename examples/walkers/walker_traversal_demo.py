"""
Walker traversal demonstration for jvspatial core module.

This example shows how walkers traverse nodes along edges in the
jvspatial object-spatial ORM architecture:
- Objects: Simple units of information stored in database
- Nodes: Modified objects designed to be connected by edges and visited by walkers
- Edges: Connect nodes
- Walkers: Traverse nodes along edges
"""

import asyncio

from pydantic import Field

from jvspatial.core import Edge, Node, Root, Walker, on_visit


# Define custom node types
class City(Node):
    """City node that can be visited by walkers."""

    name: str = Field(default="")
    population: int = Field(default=0)
    visited_count: int = Field(default=0)


class Highway(Edge):
    """Highway edge connecting cities."""

    distance: float = Field(default=0.0)
    lanes: int = Field(default=2)


# Define custom walker types
class TouristWalker(Walker):
    """Walker that visits cities and tracks its journey."""

    cities_visited: list = Field(default_factory=list)
    total_distance: float = Field(default=0.0)

    @on_visit(City)
    async def visit_city(self, here: City):
        """Called when walker visits a city."""
        print(f"🚶 Tourist visiting {here.name} (pop: {here.population:,})")

        # Track the visit
        self.cities_visited.append(here.name)
        here.visited_count += 1
        await here.save()

        # Add neighboring cities to visit queue
        neighbors = await here.neighbors(limit=2)
        unvisited_neighbors = [
            n for n in neighbors if n.name not in self.cities_visited
        ]

        if unvisited_neighbors:
            print(f"   📍 Found {len(unvisited_neighbors)} unvisited neighbors")
            await self.visit(unvisited_neighbors)

    @on_visit(Highway)
    async def traverse_highway(self, highway: Highway):
        """Called when walker traverses a highway."""
        print(
            f"🛣️  Traversing highway ({highway.distance} miles, {highway.lanes} lanes)"
        )
        self.total_distance += highway.distance


class DeliveryWalker(Walker):
    """Walker that delivers packages to cities."""

    packages: int = Field(default=5)
    deliveries_made: list = Field(default_factory=list)

    @on_visit(City)
    async def deliver_package(self, here: City):
        """Called when walker visits a city for delivery."""
        if self.packages > 0:
            print(f"📦 Delivery walker delivering package to {here.name}")
            self.packages -= 1
            self.deliveries_made.append(here.name)

            if self.packages == 0:
                print("📦 All packages delivered!")
                # Walker can pause or return to base
                return

            # Continue to next city
            neighbors = await here.neighbors(limit=1)
            undelivered = [n for n in neighbors if n.name not in self.deliveries_made]
            if undelivered:
                await self.visit(undelivered[0])


async def demonstrate_walker_traversal():
    """Demonstrate walker-based graph traversal."""

    print("🏙️  jvspatial Walker Traversal Demonstration\n")

    # 1. Create a network of cities
    print("1️⃣ Building city network:")
    new_york = City(name="New York", population=8000000)
    chicago = City(name="Chicago", population=2700000)
    denver = City(name="Denver", population=715000)
    seattle = City(name="Seattle", population=750000)

    # Connect cities with highways
    await new_york.connect(chicago, Highway, distance=790, lanes=4)
    await chicago.connect(denver, Highway, distance=920, lanes=4)
    await denver.connect(seattle, Highway, distance=1320, lanes=2)
    await seattle.connect(new_york, Highway, distance=2850, lanes=4)  # Long route

    print(
        f"   ✅ Created network with {new_york.connection_count} connections from New York"
    )

    # 2. Tourist Walker - explores the network
    print("\n2️⃣ Tourist Walker exploration:")
    tourist = TouristWalker()

    # Spawn the walker at New York
    await tourist.spawn(start=new_york)

    print(
        f"   🎯 Tourist visited {len(tourist.cities_visited)} cities: {tourist.cities_visited}"
    )
    print(f"   📏 Total distance traveled: {tourist.total_distance} miles")

    # 3. Delivery Walker - specific mission
    print("\n3️⃣ Delivery Walker mission:")
    delivery = DeliveryWalker(packages=3)

    # Start delivery route from Chicago
    await delivery.spawn(start=chicago)

    print(
        f"   📦 Delivered to {len(delivery.deliveries_made)} cities: {delivery.deliveries_made}"
    )
    print(f"   📦 Packages remaining: {delivery.packages}")

    # 4. Check visit counts
    print("\n4️⃣ Visit statistics:")
    for city in [new_york, chicago, denver, seattle]:
        print(f"   🏙️  {city.name}: {city.visited_count} visits")

    # 5. Multiple walkers from root
    print("\n5️⃣ Multiple walkers from root node:")
    root = await Root.get()

    # Connect some cities to root for demonstration
    await root.connect(new_york)
    await root.connect(seattle)

    # Spawn multiple walkers from root
    walker1 = TouristWalker()
    walker2 = DeliveryWalker(packages=2)

    # Both start from root but will take different paths
    await walker1.spawn()  # No start node = uses root
    await walker2.spawn()  # No start node = uses root

    print(f"   🚶 Walker1 visited: {walker1.cities_visited}")
    print(f"   📦 Walker2 delivered to: {walker2.deliveries_made}")

    print("\n✨ Walker traversal demonstration complete!")
    print("\n📋 Key Concepts Demonstrated:")
    print("   • Walkers traverse nodes along edges")
    print("   • Nodes are designed to be visited by walkers")
    print("   • Walkers can carry state and make decisions")
    print("   • Multiple walker types can traverse the same graph")
    print("   • Walkers use spawn() to start and visit() to traverse")


if __name__ == "__main__":
    asyncio.run(demonstrate_walker_traversal())
