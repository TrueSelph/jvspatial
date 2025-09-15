"""Example graph traversal using jvspatial library."""

import asyncio
import math
from typing import List, Optional

from jvspatial.core.entities import (
    Edge,
    Node,
    Root,
    Walker,
    on_exit,
    on_visit,
)


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates in kilometers using Haversine formula."""
    earth_radius = 6371  # Earth's radius in kilometers
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius * c


async def find_nearby_cities(latitude: float, longitude: float, radius_km: float = 10.0) -> List["City"]:
    """Find cities within a specified radius of coordinates."""
    all_cities = await City.all()
    nearby = []
    
    for city in all_cities:
        if hasattr(city, 'latitude') and hasattr(city, 'longitude'):
            distance = calculate_distance(latitude, longitude, city.latitude, city.longitude)
            if distance <= radius_km:
                nearby.append(city)
    return nearby


async def find_cities_in_bounds(min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> List["City"]:
    """Find cities within a bounding box."""
    all_cities = await City.all()
    bounded = []
    
    for city in all_cities:
        if hasattr(city, 'latitude') and hasattr(city, 'longitude'):
            if min_lat <= city.latitude <= max_lat and min_lon <= city.longitude <= max_lon:
                bounded.append(city)
    return bounded


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

    length: Optional[float] = None
    lanes: Optional[int] = None


class Railroad(Edge):
    """Represents a railroad connection between cities."""

    electrified: bool


# Custom walker types
class Tourist(Walker):
    """Walker that visits cities via highways."""

    @on_visit(City)
    async def visit_city(self: "Tourist", here: City) -> None:
        """Visit a city and traverse connected cities via highways."""
        self.response.setdefault("visited", [])
        self.response["visited"].append(here.name)
        print(f"Tourist visiting {here.name} (pop: {here.population})")

        # Visit connected cities
        neighbors_query = await here.nodes(direction="out")
        neighbors = await neighbors_query.filter(edge="Highway")
        print(f"Found {len(neighbors)} highway neighbors from {here.name}")
        for i, node in enumerate(neighbors):
            print(f"  {i+1}. {node.name} (id: {node.id})")

        to_visit = [n for n in neighbors if n.name not in self.response["visited"]]
        print(f"Visiting {len(to_visit)} new cities: {[n.name for n in to_visit]}")
        await self.visit(to_visit)


class FreightTrain(Walker):
    """Walker that loads cargo at specific cities."""

    @on_visit(City)
    async def load_cargo(self: "FreightTrain", here: City) -> None:
        """Load cargo based on the visited city."""
        self.response.setdefault("cargo", [])
        if here.name == "Chicago":
            self.response["cargo"].append("Manufactured goods")
            print("Loaded manufactured goods in Chicago")
        elif here.name == "Kansas City":
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
    root = await Root.get()  # type: ignore[call-arg]

    # Create and save city nodes with spatial data using new async pattern
    chicago = await City.create(
        name="Chicago", population=2697000, latitude=41.8781, longitude=-87.6298
    )

    st_louis = await City.create(
        name="St. Louis", population=300576, latitude=38.6270, longitude=-90.1994
    )

    kansas_city = await City.create(
        name="Kansas City", population=508090, latitude=39.0997, longitude=-94.5786
    )

    # Create edges with custom properties
    await chicago.connect(st_louis, edge=Highway, length=297, lanes=4, direction="out")
    await st_louis.connect(
        kansas_city, edge=Highway, length=248, lanes=4, direction="out"
    )
    await chicago.connect(kansas_city, edge=Railroad, electrified=True, direction="out")

    # Connect all cities to root node with generic edges
    if root:
        for city in [chicago, st_louis, kansas_city]:
            await root.connect(city)

    print("Created cities: Chicago, St. Louis, Kansas City")
    print(
        "Created connections: Chicago-St.Louis highway, St.Louis-Kansas City highway, Chicago-Kansas City railroad"
    )
    print("Connected all cities to root node with generic edges")

    print("\n=== DEMONSTRATING SPATIAL QUERIES ===")
    # Query cities using new schema
    # Query cities using entity methods
    all_cities = await Node.all()
    midwest_cities = [
        city
        for city in all_cities
        if isinstance(city, City)
        and 35 <= city.latitude <= 45
        and -95 <= city.longitude <= -85
    ]
    midwest_names = [city.name for city in midwest_cities]
    print(f"Cities in Midwest region: {', '.join(midwest_names)}")

    # Query highways using entity methods
    all_edges = await Edge.all()
    highways = [
        edge for edge in all_edges if isinstance(edge, Highway) and edge.length is not None and edge.length > 250
    ]
    print(f"Highways longer than 250 miles: {len(highways)}")

    # Demonstrate new spatial query capabilities
    print("\n=== ENHANCED SPATIAL QUERIES ===")

    # Find cities within 500km of Chicago using local utility function
    chicago_coords = (41.8781, -87.6298)
    nearby_cities = await find_nearby_cities(chicago_coords[0], chicago_coords[1], 500)
    nearby_names = [city.name for city in nearby_cities if isinstance(city, City)]
    print(f"Cities within 500km of Chicago: {', '.join(nearby_names)}")

    # Find cities in a specific bounding box (Great Lakes region) using local utility function
    great_lakes_cities = await find_cities_in_bounds(40.0, 50.0, -95.0, -75.0)
    gl_names = [city.name for city in great_lakes_cities if isinstance(city, City)]
    print(f"Cities in Great Lakes region: {', '.join(gl_names)}")

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

    try:
        error_walker = ErrorWalker()
        await error_walker.spawn(start=chicago)
    except Exception as e:
        print(f"Error during traversal: {str(e)}")
    print("Error handling demonstration complete")


if __name__ == "__main__":
    asyncio.run(main())
