"""
Walker traversal demonstration for jvspatial core module.

This example shows how walkers traverse nodes along edges in the
jvspatial object-spatial ORM architecture:
- Objects: Simple units of information stored in database
- Nodes: Modified objects designed to be connected by edges and visited by walkers
- Edges: Connect nodes
- Walkers: Traverse nodes along edges

This demo demonstrates:
1. Creating nodes using entity-centric operations
2. Connecting nodes with edges
3. Traversing the graph using walkers
4. Walker state management and decision-making
"""

import asyncio
import os

from pydantic import Field

from jvspatial.core import Edge, GraphContext, Node, Root, Walker, on_visit
from jvspatial.db import create_database


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

    @on_visit(Root)
    async def visit_root(self, here: Root):
        """Called when walker visits root - continue to connected nodes."""
        print("🚶 Tourist at root node, exploring connected cities...")
        # Get connected nodes (defaults to direction="out" for forward traversal)
        connected_nodes = await here.nodes()
        city_nodes = [
            n
            for n in connected_nodes
            if isinstance(n, City) and n.name not in self.cities_visited
        ]
        if city_nodes:
            await self.visit(city_nodes)

    @on_visit(City)
    async def visit_city(self, here: City):
        """Called when walker visits a city."""
        print(f"🚶 Tourist visiting {here.name} (pop: {here.population:,})")

        # Track the visit
        self.cities_visited.append(here.name)
        here.visited_count += 1
        await here.save()

        # Get connected cities via edges (defaults to direction="out" for forward traversal)
        connected_nodes = await here.nodes()
        unvisited_neighbors = [
            n
            for n in connected_nodes
            if isinstance(n, City) and n.name not in self.cities_visited
        ]

        if unvisited_neighbors:
            print(f"   📍 Found {len(unvisited_neighbors)} unvisited neighbors")
            # Use visit() to continue traversal
            await self.visit(unvisited_neighbors)
        else:
            # No more unvisited neighbors, traversal naturally ends
            print(f"   ✅ Completed traversal from {here.name}")

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

    @on_visit(Root)
    async def visit_root(self, here: Root):
        """Called when walker visits root - continue to connected cities."""
        print("📦 Delivery walker at root node, starting deliveries...")
        # Get connected nodes (defaults to direction="out" for forward traversal)
        connected_nodes = await here.nodes()
        city_nodes = [
            n
            for n in connected_nodes
            if isinstance(n, City)
            and n.name not in self.deliveries_made
            and self.packages > 0
        ]
        if city_nodes:
            await self.visit(city_nodes)

    @on_visit(City)
    async def deliver_package(self, here: City):
        """Called when walker visits a city for delivery."""
        if self.packages > 0:
            print(f"📦 Delivery walker delivering package to {here.name}")
            self.packages -= 1
            self.deliveries_made.append(here.name)

            if self.packages == 0:
                print("📦 All packages delivered!")
                # Walker stops when all packages delivered
                return

            # Continue to next city using visit() (defaults to direction="out" for forward traversal)
            connected_nodes = await here.nodes()
            undelivered = [
                n
                for n in connected_nodes
                if isinstance(n, City) and n.name not in self.deliveries_made
            ]
            if undelivered:
                # Use visit() to continue traversal
                await self.visit(undelivered)
            else:
                # No more cities to deliver to
                print(f"   ✅ Completed deliveries from {here.name}")


async def demonstrate_walker_traversal():
    """Demonstrate walker-based graph traversal."""

    # Initialize database context
    db_type = os.getenv("JVSPATIAL_DB_TYPE", "json")
    database = create_database(db_type=db_type, base_path="./jvdb")
    ctx = GraphContext(database=database)

    # Set as default context for entity-centric operations
    from jvspatial.core.context import set_default_context

    set_default_context(ctx)

    print("🏙️  jvspatial Walker Traversal Demonstration\n")

    # 1. Create a network of cities using entity-centric operations
    print("1️⃣ Building city network:")
    new_york = await City.create(name="New York", population=8000000, visited_count=0)
    chicago = await City.create(name="Chicago", population=2700000, visited_count=0)
    denver = await City.create(name="Denver", population=715000, visited_count=0)
    seattle = await City.create(name="Seattle", population=750000, visited_count=0)

    # Connect cities with highways (creating a tree structure, no cycles)
    # Default direction="out" creates unidirectional edges (bidirectional=False) to prevent cycles
    await new_york.connect(chicago, Highway, distance=790, lanes=4)
    await chicago.connect(denver, Highway, distance=920, lanes=4)
    await chicago.connect(
        seattle, Highway, distance=1730, lanes=4
    )  # Branch from Chicago

    # IMPORTANT: Connect at least one node to root for spawn() to work
    root = await Root.get()
    await root.connect(
        new_york
    )  # Connect New York to root (defaults to direction="out", unidirectional)

    # Get connection count (using nodes() which defaults to direction="out")
    connection_count = len(await new_york.nodes())
    print(f"   ✅ Created network with {connection_count} connections from New York")
    print(f"   ✅ New York connected to root node")

    # 2. Tourist Walker - explores the network
    print("\n2️⃣ Tourist Walker exploration:")
    tourist = TouristWalker()

    # Start the walker at New York using spawn()
    await tourist.spawn(new_york)

    print(
        f"   🎯 Tourist visited {len(tourist.cities_visited)} cities: {tourist.cities_visited}"
    )
    print(f"   📏 Total distance traveled: {tourist.total_distance} miles")

    # 3. Delivery Walker - specific mission
    print("\n3️⃣ Delivery Walker mission:")
    delivery = DeliveryWalker(packages=3)

    # Start delivery route from Chicago using spawn()
    await delivery.spawn(chicago)

    print(
        f"   📦 Delivered to {len(delivery.deliveries_made)} cities: {delivery.deliveries_made}"
    )
    print(f"   📦 Packages remaining: {delivery.packages}")

    # 4. Check visit counts (reload cities to get updated counts)
    print("\n4️⃣ Visit statistics:")
    for city_id in [new_york.id, chicago.id, denver.id, seattle.id]:
        city = await City.get(city_id)
        if city:
            print(f"   🏙️  {city.name}: {city.visited_count} visits")

    # 5. Multiple walkers from root
    print("\n5️⃣ Multiple walkers from root node:")
    # Note: root is already available from step 1

    # Create fresh walkers for root traversal demonstration
    walker1 = TouristWalker()
    walker2 = DeliveryWalker(packages=3)  # Enough packages for all cities from root

    # Both start from root - spawn() with no argument defaults to root
    print("   Starting walkers from root (no argument = defaults to root)...")
    await walker1.spawn()  # Defaults to root
    await walker2.spawn()  # Defaults to root

    print(f"   🚶 Walker1 visited: {walker1.cities_visited}")
    print(f"   📦 Walker2 delivered to: {walker2.deliveries_made}")

    print("\n✨ Walker traversal demonstration complete!")
    print("\n📋 Key Concepts Demonstrated:")
    print("   • Entity-centric operations: City.create() for creating nodes")
    print("   • Node connections: node.connect() for creating edges between nodes")
    print(
        "   • Root connection: At least one node connected to root for spawn() default"
    )
    print(
        "   • Walker spawn: walker.spawn(node) to start at specific node, walker.spawn() defaults to root"
    )
    print("   • Graph traversal: walker.visit(node.nodes()) to continue traversal")
    print(
        "   • Node queries: node.nodes() defaults to direction='out' (forward traversal only, use direction='both' for bidirectional)"
    )
    print("   • Walkers traverse nodes along edges")
    print("   • Nodes are designed to be visited by walkers")
    print("   • Walkers can carry state and make decisions")
    print("   • Multiple walker types can traverse the same graph")


if __name__ == "__main__":
    asyncio.run(demonstrate_walker_traversal())
