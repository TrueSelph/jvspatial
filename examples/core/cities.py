"""
Example demonstrating core jvspatial functionality using a city/road network.

This example shows:
1. Creating Node and Edge types
2. Creating and connecting nodes
3. Using a Walker for graph traversal
4. Collecting and reporting data
"""

import asyncio
from typing import List, Optional

from jvspatial.core import Edge, Node, Walker, on_exit, on_visit


class City(Node):
    """A city node with spatial and demographic data."""

    name: str = ""
    population: int = 0
    coordinates: tuple[float, float] = (0.0, 0.0)
    is_capital: bool = False
    state: str = ""


class Highway(Edge):
    """A highway connecting cities."""

    name: str = ""
    distance: float = 0.0
    speed_limit: int = 65
    num_lanes: int = 2
    is_toll_road: bool = False


class CityAnalyzer(Walker):
    """Walker that analyzes connected cities."""

    def __init__(self, min_population: int = 0) -> None:
        super().__init__()
        self.min_population = min_population
        self.total_population = 0
        self.total_distance = 0.0
        self.capitals_found = 0

    @on_visit(City)
    async def analyze_city(self, here: City) -> None:
        """Process each city we visit."""
        print(f"\nVisiting {here.name}, {here.state}")
        print(f"  Population: {here.population:,}")
        print(f"  Location: {here.coordinates}")

        # Update statistics
        self.total_population += here.population
        if here.is_capital:
            self.capitals_found += 1

        # Skip small cities if we have a population filter
        if here.population < self.min_population:
            print(f"  Skipping {here.name} - below population threshold")
            await self.skip()
            return

        # Get connected cities via highways
        connected = await here.nodes(
            node="City",  # Only look for City nodes
            edge="Highway",  # Only follow Highway edges
            direction="out",  # Follow outgoing connections
        )

        # Update total distance traveled
        for city in connected:
            # Get the highway between cities
            context = await here.get_context()
            edges = await context.find_edges_between(here.id, city.id, Highway)
            if edges:
                highway = edges[0]  # Take first highway found
                self.total_distance += highway.distance
                print(f"  -> {city.name} via {highway.name} ({highway.distance} miles)")

        # Continue to connected cities
        await self.visit(connected)

    @on_exit
    async def generate_report(self) -> None:
        """Generate final statistics when traversal is complete."""
        print("\nFinal Report:")
        await self.report(
            {
                "total_cities": len(self._visited_nodes),
                "total_population": self.total_population,
                "total_distance": self.total_distance,
                "capitals_visited": self.capitals_found,
                "min_population_filter": self.min_population,
            }
        )


async def create_sample_network() -> City:
    """Create a sample network of cities and highways."""

    # Create cities
    nyc = await City.create(
        name="New York City",
        state="NY",
        population=8_400_000,
        coordinates=(40.7128, -74.0060),
    )

    boston = await City.create(
        name="Boston",
        state="MA",
        population=675_000,
        coordinates=(42.3601, -71.0589),
        is_capital=True,
    )

    albany = await City.create(
        name="Albany",
        state="NY",
        population=99_000,
        coordinates=(42.6526, -73.7562),
        is_capital=True,
    )

    # Create and connect highways
    i95 = await Highway.create(
        source=nyc.id,
        target=boston.id,
        name="I-95",
        distance=215.0,
        speed_limit=65,
        num_lanes=4,
    )
    await nyc.connect(boston, edge=i95)
    print(f"Created {i95.name}: {i95.distance} miles")

    i87 = await Highway.create(
        source=nyc.id,
        target=albany.id,
        name="I-87",
        distance=155.0,
        speed_limit=65,
        num_lanes=3,
    )
    await nyc.connect(albany, edge=i87)
    print(f"Created {i87.name}: {i87.distance} miles")

    i90 = await Highway.create(
        source=albany.id,
        target=boston.id,
        name="I-90",
        distance=170.0,
        speed_limit=65,
        num_lanes=3,
        is_toll_road=True,
    )
    await albany.connect(boston, edge=i90)
    print(f"Created {i90.name}: {i90.distance} miles")

    return nyc  # Return NYC as our starting point


async def main():
    """Run the example."""
    # Create our network
    print("Creating city network...")
    start_city = await create_sample_network()

    # Create and run our walker
    print("\nStarting city analysis...")
    walker = CityAnalyzer(min_population=500_000)  # Skip cities under 500k
    result = await walker.spawn(start_city)

    # Print the walker's report
    print("\nWalker Report:")
    for item in result.get_report():
        if isinstance(item, dict):
            for key, value in item.items():
                if isinstance(value, (int, float)) and value > 1000:
                    # Format large numbers
                    print(f"  {key}: {value:,}")
                else:
                    print(f"  {key}: {value}")
        else:
            print(f"  {item}")


if __name__ == "__main__":
    asyncio.run(main())
