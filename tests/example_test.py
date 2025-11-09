import asyncio

from jvspatial.core import on_exit, on_visit
from jvspatial.core.entities import Edge, Node, Walker


# Define nodes and edges
class City(Node):
    name: str = ""
    population: int = 0
    coordinates: tuple[float, float] = (0.0, 0.0)


class Highway(Edge):
    name: str = ""
    distance: float = 0.0
    speed_limit: int = 65


# Define walker
class CityAnalyzer(Walker):
    def __init__(self):
        super().__init__()
        self.total_population = 0

    @on_visit(City)
    async def analyze_city(self, here: City):
        print(f"Visiting city: {here.name} (pop: {here.population})")
        # Process each city node
        self.total_population += here.population

        # Find connected cities via highways
        connected = await here.nodes(
            node="City",  # Only City nodes
            edge=Highway,  # Only Highway edges
            direction="out",  # Outgoing connections
        )
        print(f"Found {len(connected)} connected cities from {here.name}")

        # Continue walking to connected cities
        await self.visit(connected)

    @on_exit
    async def generate_report(self):
        print("Generating final report...")
        # Report each value separately for clarity
        self.report(f"Total population: {self.total_population}")
        self.report(f"Cities visited: {len(self._visited_nodes)}")


async def main():
    # Create sample cities
    nyc = await City.create(
        name="New York", population=8_400_000, coordinates=(40.7128, -74.0060)
    )

    boston = await City.create(
        name="Boston", population=675_000, coordinates=(42.3601, -71.0589)
    )

    # Connect cities with a highway
    print("Creating highway...")
    i95 = await Highway.create(
        src=nyc,  # Source node
        dst=boston,  # Destination node
        name="I-95",
        distance=215.0,
        speed_limit=65,
    )
    print(f"Highway created: {i95.name}")

    # Explicitly connect nodes
    print("Connecting cities...")
    await nyc.connect(boston, edge=i95)
    print("Cities connected")

    # Create and run walker
    walker = CityAnalyzer()
    result = await walker.spawn(nyc)  # Start from NYC

    # Print report
    print("\nWalker Report:")
    report = result.get_report()
    for item in report:
        print(f"  {item}")


if __name__ == "__main__":
    asyncio.run(main())
