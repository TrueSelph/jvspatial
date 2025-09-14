"""Example graph traversal using jvspatial library."""

import asyncio

from jvspatial.core.entities import (
    Edge,
    Node,
    RootNode,
    Walker,
    on_exit,
    on_visit,
)


# Custom node types for demo
class City(Node):
    """Represents a city with geographic attributes."""

    name: str
    population: int
    latitude: float
    longitude: float

    @on_visit
    def on_visited(self: "City", visitor: Walker) -> None:
        """Log when visited by a walker."""
        print(f"Being visited by {visitor.id}")


class Highway(Edge):
    """Represents a highway connection between cities."""

    length: float
    lanes: int


class Railroad(Edge):
    """Represents a railroad connection between cities."""

    electrified: bool


# Custom walker types
class Tourist(Walker):
    """Walker that visits cities via highways."""

    @on_visit(City)
    async def visit_city(self: "Tourist", visitor: City) -> None:
        """Visit a city and traverse connected cities via highways."""
        if "visited" not in self.response:
            self.response["visited"] = []
        self.response["visited"].append(visitor.name)
        print(f"Tourist visiting {visitor.name} (pop: {visitor.population})")

        # Visit connected cities
        neighbors = await (await visitor.nodes(direction="out")).filter(edge=Highway)
        await self.visit(
            [n for n in neighbors if n.name not in self.response["visited"]]
        )


class FreightTrain(Walker):
    """Walker that loads cargo at specific cities."""

    @on_visit(City)
    async def load_cargo(self: "FreightTrain", visitor: City) -> None:
        """Load cargo based on the visited city."""
        if "cargo" not in self.response:
            self.response["cargo"] = []
        if visitor.name == "Chicago":
            self.response["cargo"].append("Manufactured goods")
            print("Loaded manufactured goods in Chicago")
        elif visitor.name == "Kansas City":
            self.response["cargo"].append("Agricultural products")
            print("Loaded agricultural products in Kansas City")

    @on_exit
    async def final_delivery(self: "FreightTrain") -> None:
        """Deliver all loaded cargo at the end of traversal."""
        cargo_list = self.response.get("cargo", [])
        if cargo_list:
            print(f"Delivered cargo: {', '.join(cargo_list)}")


async def main() -> None:
    """Demonstrate graph operations."""
    # Database auto-configured on first use
    print("\n=== DEMONSTRATING GRAPH CREATION ===")
    # Create root node
    root = await RootNode.get()  # type: ignore[call-arg]

    # Create city nodes with spatial data
    chicago = City(
        name="Chicago", population=2697000, latitude=41.8781, longitude=-87.6298
    )
    st_louis = City(
        name="St. Louis", population=300576, latitude=38.6270, longitude=-90.1994
    )
    kansas_city = City(
        name="Kansas City", population=508090, latitude=39.0997, longitude=-94.5786
    )

    # Create edges with custom properties
    await chicago.connect(st_louis, Highway, length=297, lanes=4, bidirectional=False)
    await st_louis.connect(
        kansas_city, Highway, length=248, lanes=4, bidirectional=False
    )
    await chicago.connect(kansas_city, Railroad, electrified=True, bidirectional=False)

    # Connect all cities to root node with generic edges
    for city in [chicago, st_louis, kansas_city]:
        await root.connect(city)

    print("Created cities: Chicago, St. Louis, Kansas City")
    print(
        "Created connections: Chicago-St.Louis highway, St.Louis-Kansas City highway, Chicago-Kansas City railroad"
    )
    print("Connected all cities to root node with generic edges")

    print("\n=== DEMONSTRATING SPATIAL QUERIES ===")
    # Query cities using new schema
    midwest_cities = await RootNode.get_db().find(
        "node",
        {
            "name": "City",
            "context.latitude": {"$gte": 35, "$lte": 45},
            "context.longitude": {"$gte": -95, "$lte": -85},
        },
    )
    midwest_names = [city["context"]["name"] for city in midwest_cities]
    print(f"Cities in Midwest region: {', '.join(midwest_names)}")

    # Query highways using new schema
    highways = await RootNode.get_db().find(
        "edge", {"name": "Highway", "context.length": {"$gt": 250}}
    )
    print(f"Highways longer than 250 miles: {len(highways)}")

    print("\n=== DEMONSTRATING ASYNC TRAVERSAL WITH CONCURRENT WALKERS ===")

    # Create walkers
    tourist = Tourist()
    freight_train = FreightTrain()

    # Run walkers concurrently
    print("Starting concurrent walkers...")
    await asyncio.gather(
        tourist.spawn(start=chicago), freight_train.spawn(start=chicago)
    )

    print(f"Tourist visited: {', '.join(tourist.response.get('visited', []))}")
    print(f"Freight train cargo: {', '.join(freight_train.response.get('cargo', []))}")

    print("\n=== DEMONSTRATING ERROR HANDLING ===")

    class ErrorWalker(Walker):
        """Walker that intentionally causes errors."""

        @on_visit(City)
        async def cause_error(self: "ErrorWalker", here: City) -> None:
            """Raise an error during traversal."""
            print(f"Visiting here {here.id}")
            # Simulate an error during traversal
            raise ValueError("Simulated traversal error")

    error_walker = ErrorWalker()
    await error_walker.spawn(start=chicago)
    print("Error handling demonstration complete")


if __name__ == "__main__":
    asyncio.run(main())
