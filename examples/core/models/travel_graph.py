"""Travel Graph Example - Modern jvspatial Patterns

Demonstrates modern jvspatial conventions and spatial graph operations.
Shows entity-centric CRUD, MongoDB-style queries, walker patterns,
and spatial analysis capabilities.

Features demonstrated:
- Entity-centric CRUD operations (City.create(), City.find(), etc.)
- MongoDB-style spatial and attribute queries
- Modern walker patterns with proper parameter naming
- Spatial analysis functions with database-level optimization
- Advanced GraphContext patterns for complex scenarios
- Concurrent walker operations
- Error handling and recovery
"""

import asyncio
import math
from typing import Any, Dict, List, Optional

from jvspatial.core import Edge, Node, Root, Walker, on_exit, on_visit


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


async def find_nearby_cities(
    latitude: float, longitude: float, radius_km: float = 10.0
) -> List["City"]:
    """Find cities within a specified radius of coordinates using entity-centric queries."""
    # RECOMMENDED: Use entity-centric find instead of Node.all()
    all_cities = await City.find({})
    nearby = []

    for city in all_cities:
        distance = calculate_distance(
            latitude, longitude, city.latitude, city.longitude
        )
        if distance <= radius_km:
            nearby.append(city)
    return nearby


async def find_cities_in_bounds(
    min_lat: float, max_lat: float, min_lon: float, max_lon: float
) -> List["City"]:
    """Find cities within a bounding box using MongoDB-style spatial queries."""
    # RECOMMENDED: Use MongoDB-style spatial queries for complex filtering
    bounded_cities = await City.find(
        {
            "$and": [
                {"context.latitude": {"$gte": min_lat, "$lte": max_lat}},
                {"context.longitude": {"$gte": min_lon, "$lte": max_lon}},
            ]
        }
    )
    return bounded_cities


# ============== NODE DEFINITIONS ==============


class City(Node):
    """Represents a city with geographic attributes and population data."""

    name: str = ""
    population: int = 0
    latitude: float = 0.0
    longitude: float = 0.0
    founded_year: Optional[int] = None
    timezone: str = "UTC"

    @on_visit(Walker)
    def on_visited(self: "City", visitor: Walker) -> None:
        """Log when visited by a walker."""
        print(
            f"🏙️ {self.name} being visited by {visitor.__class__.__name__} ({visitor.id})"
        )


class Highway(Edge):
    """Represents a highway connection between cities."""

    length: Optional[float] = None  # Length in miles
    lanes: Optional[int] = None
    speed_limit: int = 70  # mph
    toll_road: bool = False
    highway_number: str = ""


class Railroad(Edge):
    """Represents a railroad connection between cities."""

    electrified: bool = False
    gauge: str = "standard"  # track gauge type
    freight_capacity: Optional[int] = None  # tons per train


# ============== WALKER DEFINITIONS ==============


class Tourist(Walker):
    """Walker that visits cities via highways and explores road networks."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.visited_cities = []  # Track visited cities internally

    @on_visit(City)
    async def visit_city(self: "Tourist", here: City) -> None:
        """Visit a city and traverse connected cities via highways.

        Args:
            here: The visited City node
        """
        if here.name not in self.visited_cities:
            self.visited_cities.append(here.name)
            print(f"🎅 Tourist visiting {here.name} (pop: {here.population:,})")

            # Report the visit
            await self.report(
                {
                    "city_visited": {
                        "name": here.name,
                        "population": here.population,
                        "location": {"lat": here.latitude, "lon": here.longitude},
                    }
                }
            )

            # RECOMMENDED: Use nodes() method with semantic filtering
            highway_neighbors = await here.nodes(direction="out", edge=[Highway])
            print(f"  🛣️ Found {len(highway_neighbors)} highway connections")

            # Show details about available routes
            highway_edges = await here.edges(direction="out")
            for edge in highway_edges:
                if isinstance(edge, Highway) and edge.length:
                    target = await City.get(edge.target)
                    if target and target.name not in self.visited_cities:
                        print(
                            f"    → {target.name} via Highway ({edge.length} miles, {edge.lanes} lanes)"
                        )

            # Visit unvisited cities
            to_visit = [
                n for n in highway_neighbors if n.name not in self.visited_cities
            ]
            if to_visit:
                print(f"  📍 Next destinations: {[n.name for n in to_visit]}")
                await self.visit(to_visit)


class FreightTrain(Walker):
    """Walker that loads and transports cargo between cities via railroad."""

    max_cargo_capacity: int = 5000  # tons
    current_cargo_weight: int = 0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.route_cities = []  # Track visited cities for route
        self.cargo_list = []  # Track cargo loaded

    @on_visit(City)
    async def load_cargo(self: "FreightTrain", here: City) -> None:
        """Load cargo based on the visited city's characteristics.

        Args:
            here: The visited City node
        """
        self.route_cities.append(here.name)

        # Load cargo based on city characteristics
        cargo_loaded = False
        if (
            here.name == "Chicago"
            and self.current_cargo_weight < self.max_cargo_capacity
        ):
            chicago_cargo: Dict[str, Any] = {
                "type": "Manufactured goods",
                "weight": 2000,
                "destination": "Kansas City",
            }
            self.cargo_list.append(chicago_cargo)
            self.current_cargo_weight += chicago_cargo["weight"]
            print(
                f"🚂 Loaded {chicago_cargo['weight']} tons of {chicago_cargo['type']} in {here.name}"
            )
            # Report cargo loaded
            await self.report(
                {
                    "cargo_loaded": {
                        "city": here.name,
                        "type": chicago_cargo["type"],
                        "weight": chicago_cargo["weight"],
                        "destination": chicago_cargo["destination"],
                    }
                }
            )
            cargo_loaded = True
        elif (
            here.name == "Kansas City"
            and self.current_cargo_weight < self.max_cargo_capacity
        ):
            kansas_cargo: Dict[str, Any] = {
                "type": "Agricultural products",
                "weight": 1500,
                "destination": "St. Louis",
            }
            self.cargo_list.append(kansas_cargo)
            self.current_cargo_weight += kansas_cargo["weight"]
            print(
                f"🚂 Loaded {kansas_cargo['weight']} tons of {kansas_cargo['type']} in {here.name}"
            )
            # Report cargo loaded
            await self.report(
                {
                    "cargo_loaded": {
                        "city": here.name,
                        "type": kansas_cargo["type"],
                        "weight": kansas_cargo["weight"],
                        "destination": kansas_cargo["destination"],
                    }
                }
            )
            cargo_loaded = True

        if not cargo_loaded:
            print(f"🚂 Passing through {here.name} - no cargo to load")

        # Continue along railroad connections
        rail_neighbors = await here.nodes(direction="out", edge=[Railroad])
        unvisited = [n for n in rail_neighbors if n.name not in self.route_cities]
        if unvisited:
            await self.visit(unvisited)

    @on_exit
    async def final_delivery(self: "FreightTrain") -> None:
        """Complete the freight delivery and provide summary.

        Called when walker completes traversal.
        """
        if self.cargo_list:
            total_weight = sum(c["weight"] for c in self.cargo_list)
            cargo_types = [f"{c['weight']}t {c['type']}" for c in self.cargo_list]
            print(f"📦 Freight delivery complete! Total cargo: {total_weight} tons")
            print(f"  Cargo manifest: {', '.join(cargo_types)}")
            print(f"  Route taken: {' → '.join(self.route_cities)}")

            # Report final delivery summary
            await self.report(
                {
                    "delivery_summary": {
                        "total_weight": total_weight,
                        "cargo_items": len(self.cargo_list),
                        "route": self.route_cities,
                        "cargo_manifest": self.cargo_list,
                    }
                }
            )
        else:
            print("🚂 Freight train completed route with no cargo")


# ============== DEMONSTRATION FUNCTIONS ==============


async def create_sample_travel_network():
    """Create sample travel network using entity-centric CRUD operations."""
    print("\n🏗️ Creating sample travel network using entity-centric methods")

    try:
        # RECOMMENDED: Use entity-centric create operations
        root = await Root.get()

        # Create cities with diverse characteristics
        cities_data = [
            {
                "name": "Chicago",
                "population": 2697000,
                "latitude": 41.8781,
                "longitude": -87.6298,
                "founded_year": 1837,
                "timezone": "America/Chicago",
            },
            {
                "name": "St. Louis",
                "population": 300576,
                "latitude": 38.6270,
                "longitude": -90.1994,
                "founded_year": 1764,
                "timezone": "America/Chicago",
            },
            {
                "name": "Kansas City",
                "population": 508090,
                "latitude": 39.0997,
                "longitude": -94.5786,
                "founded_year": 1838,
                "timezone": "America/Chicago",
            },
            {
                "name": "Denver",
                "population": 715522,
                "latitude": 39.7392,
                "longitude": -104.9903,
                "founded_year": 1858,
                "timezone": "America/Denver",
            },
        ]

        created_cities = []
        for city_data in cities_data:
            city = await City.create(**city_data)
            await root.connect(city)
            created_cities.append(city)
            print(
                f"✅ Created {city.name} (pop: {city.population:,}, founded: {city.founded_year})"
            )

        chicago, st_louis, kansas_city, denver = created_cities

        # Create highway connections with detailed attributes
        highway_connections = [
            (
                chicago,
                st_louis,
                {
                    "length": 297.0,
                    "lanes": 4,
                    "speed_limit": 70,
                    "highway_number": "I-55",
                },
            ),
            (
                st_louis,
                kansas_city,
                {
                    "length": 248.0,
                    "lanes": 4,
                    "speed_limit": 70,
                    "highway_number": "I-70",
                },
            ),
            (
                kansas_city,
                denver,
                {
                    "length": 605.0,
                    "lanes": 4,
                    "speed_limit": 75,
                    "highway_number": "I-70",
                    "toll_road": False,
                },
            ),
        ]

        for source, target, attrs in highway_connections:
            await source.connect(target, edge=Highway, direction="out", **attrs)
            print(
                f"🛣️ Connected {source.name} → {target.name} via {attrs['highway_number']} ({attrs['length']} miles)"
            )

        # Create railroad connections
        railroad_connections = [
            (
                chicago,
                kansas_city,
                {"electrified": True, "gauge": "standard", "freight_capacity": 8000},
            ),
            (
                st_louis,
                kansas_city,
                {"electrified": False, "gauge": "standard", "freight_capacity": 6000},
            ),
        ]

        for source, target, attrs in railroad_connections:
            await source.connect(target, edge=Railroad, direction="out", **attrs)
            electrified_str = (
                "electrified" if attrs["electrified"] else "non-electrified"
            )
            print(
                f"🚂 Connected {source.name} → {target.name} via {electrified_str} railroad ({attrs['freight_capacity']}t capacity)"
            )

        print(f"🎉 Travel network created with {len(created_cities)} cities")
        return created_cities

    except Exception as e:
        print(f"❌ Error creating travel network: {e}")
        return []


async def demonstrate_mongodb_queries():
    """Demonstrate MongoDB-style queries for complex filtering."""
    print(
        "\n🔍 Demonstrating MongoDB-style queries with spatial and attribute filtering"
    )

    try:
        # RECOMMENDED: Complex queries using MongoDB operators

        # Find large cities (population > 500k)
        large_cities = await City.find({"context.population": {"$gt": 500000}})
        print(
            f"✅ Found {len(large_cities)} large cities (>500k pop): {[c.name for c in large_cities]}"
        )

        # Find cities founded before 1850
        historic_cities = await City.find(
            {"context.founded_year": {"$lt": 1850, "$exists": True}}
        )
        print(
            f"✅ Found {len(historic_cities)} historic cities (founded <1850): {[c.name for c in historic_cities]}"
        )

        # Find cities in the Midwest region with specific timezone
        midwest_cities = await City.find(
            {
                "$and": [
                    {"context.latitude": {"$gte": 35.0, "$lte": 45.0}},
                    {"context.longitude": {"$gte": -95.0, "$lte": -85.0}},
                    {"context.timezone": "America/Chicago"},
                ]
            }
        )
        print(
            f"✅ Found {len(midwest_cities)} Midwest cities in Chicago timezone: {[c.name for c in midwest_cities]}"
        )

        # Find highways longer than 300 miles OR with more than 4 lanes
        long_or_wide_highways = await Highway.find(
            {"$or": [{"context.length": {"$gt": 300.0}}, {"context.lanes": {"$gt": 4}}]}
        )
        print(f"✅ Found {len(long_or_wide_highways)} highways (>300mi OR >4 lanes)")

        # Find electrified railroads with high capacity
        electrified_heavy_rail = await Railroad.find(
            {
                "$and": [
                    {"context.electrified": True},
                    {"context.freight_capacity": {"$gte": 7000}},
                ]
            }
        )
        print(
            f"✅ Found {len(electrified_heavy_rail)} electrified heavy-freight railroads"
        )

        # Demonstrate count operations
        total_cities = await City.count()
        total_highways = await Highway.count()
        total_railroads = await Railroad.count()

        print(f"\n📊 Network statistics:")
        print(f"  Cities: {total_cities}")
        print(f"  Highways: {total_highways}")
        print(f"  Railroads: {total_railroads}")

    except Exception as e:
        print(f"❌ Error in MongoDB query demonstration: {e}")


async def main() -> None:
    """Demonstrate modern jvspatial patterns with travel graph operations."""
    print("🚀 Travel Graph Example - Modern jvspatial Patterns")
    print(
        "Demonstrates entity-centric CRUD, MongoDB-style queries, and spatial analysis"
    )

    print("\n=== ENTITY-CENTRIC CRUD OPERATIONS ===")

    # Create sample travel network
    cities = await create_sample_travel_network()

    if not cities:
        print("❌ Failed to create travel network")
        return

    # Demonstrate MongoDB-style queries
    await demonstrate_mongodb_queries()

    print("\n=== SPATIAL ANALYSIS DEMONSTRATIONS ===")

    # Get a reference city for spatial queries
    chicago_results = await City.find({"context.name": "Chicago"})
    chicago = chicago_results[0] if chicago_results else None
    if not chicago:
        print("❌ Chicago not found for spatial analysis")
        return

    # Find cities within 500km of Chicago using utility function
    print(
        f"\n🌍 Spatial analysis centered on {chicago.name} ({chicago.latitude}, {chicago.longitude})"
    )
    nearby_cities = await find_nearby_cities(chicago.latitude, chicago.longitude, 500)
    nearby_names = [city.name for city in nearby_cities]
    print(f"✅ Cities within 500km of Chicago: {', '.join(nearby_names)}")

    # Find cities in Great Lakes region using bounding box
    great_lakes_cities = await find_cities_in_bounds(40.0, 50.0, -95.0, -75.0)
    gl_names = [city.name for city in great_lakes_cities]
    print(f"✅ Cities in Great Lakes region: {', '.join(gl_names)}")

    # Demonstrate highway analysis
    long_highways = await Highway.find({"context.length": {"$gt": 250.0}})
    print(f"✅ Highways longer than 250 miles: {len(long_highways)}")
    for highway in long_highways:
        source_city = await City.get(highway.source)
        target_city = await City.get(highway.target)
        if source_city and target_city:
            print(
                f"  🛣️ {source_city.name} → {target_city.name}: {highway.length} miles via {highway.highway_number}"
            )

    print("\n=== WALKER TRAVERSAL DEMONSTRATIONS ===")

    # Create and run tourist walker
    print("\n🎅 Starting Tourist walker (follows highways)")
    tourist = Tourist()
    await tourist.spawn(chicago)

    # Access walker's collected data
    tourist_report = await tourist.get_report()
    print(f"🗂️ Tourist route: {' → '.join(tourist.visited_cities)}")
    print(f"📊 Tourist collected {len(tourist_report)} reports")

    # Create and run freight train walker
    print("\n🚂 Starting FreightTrain walker (follows railroads)")
    freight_train = FreightTrain()
    await freight_train.spawn(chicago)

    # Show concurrent walker execution
    print("\n🔄 Demonstrating concurrent walker execution")
    tourist2 = Tourist()
    freight_train2 = FreightTrain()

    # Run both walkers simultaneously from different starting points
    kansas_city_results = await City.find({"context.name": "Kansas City"})
    kansas_city = kansas_city_results[0] if kansas_city_results else None
    if kansas_city:
        print(
            "Running Tourist from Chicago and FreightTrain from Kansas City simultaneously..."
        )
        await asyncio.gather(tourist2.spawn(chicago), freight_train2.spawn(kansas_city))

        # Access data from walkers
        print(f"🎅 Tourist 2 visited: {', '.join(tourist2.visited_cities)}")
        if freight_train2.cargo_list:
            cargo_summary = [
                f"{c['weight']}t {c['type']}" for c in freight_train2.cargo_list
            ]
            print(f"🚂 Freight 2 cargo: {', '.join(cargo_summary)}")
        else:
            print("🚂 Freight 2: No cargo loaded")

    print("\n=== ERROR HANDLING AND RECOVERY ===")

    class ErrorWalker(Walker):
        """Walker that demonstrates error handling during traversal."""

        @on_visit(City)
        async def cause_error(self: "ErrorWalker", here: City) -> None:
            """Demonstrate error handling during traversal.

            Args:
                here: The visited City node
            """
            print(f"⚠️ ErrorWalker visiting {here.name}")
            if here.name == "St. Louis":
                # Simulate an error at a specific location
                raise ValueError(f"Simulated network error in {here.name}")
            else:
                print(f"✅ Successfully processed {here.name}")

    try:
        print("Testing error handling in walker traversal...")
        error_walker = ErrorWalker()
        await error_walker.spawn(chicago)
    except Exception as e:
        print(f"❌ Caught expected error: {str(e)}")

    print("✅ Error handling demonstration complete - system recovered gracefully")

    # Final summary
    print("\n=== EXAMPLE SUMMARY ===")
    print("✅ Example completed successfully!")
    print("Key demonstrations:")
    print("  • Entity-centric CRUD (City.create(), City.find(), etc.)")
    print("  • MongoDB-style queries with spatial operators ($and, $or, $gte, etc.)")
    print("  • Modern walker patterns with proper parameter naming ('here' parameter)")
    print("  • Spatial analysis with bounding boxes and distance calculations")
    print("  • Concurrent walker operations with different traversal strategies")
    print("  • Comprehensive error handling and recovery")


if __name__ == "__main__":
    asyncio.run(main())
