"""
Example demonstrating spatial queries and MongoDB-style filtering.

This example shows:
1. Using MongoDB-style queries with nodes
2. Spatial queries using coordinates
3. Complex filtering with multiple conditions
4. Using the ObjectPager for large result sets
"""

import asyncio
from typing import List, Optional

from jvspatial.core import Edge, Node, ObjectPager, Walker, on_visit, paginate_objects


class Location(Node):
    """A location with spatial coordinates and metadata."""

    name: str = ""
    coordinates: tuple[float, float] = (0.0, 0.0)
    type: str = "unknown"  # restaurant, park, store, etc.
    rating: float = 0.0  # 0-5 stars
    price: int = 1  # 1-4 price level
    is_open: bool = True
    tags: List[str] = []


async def create_sample_locations():
    """Create sample location data."""
    # Create some restaurants
    await Location.create(
        name="Joe's Pizza",
        coordinates=(40.7305, -73.9952),  # NYC - Greenwich Village
        type="restaurant",
        rating=4.5,
        price=2,
        tags=["pizza", "italian", "casual"],
    )

    await Location.create(
        name="Le Bernardin",
        coordinates=(40.7616, -73.9819),  # NYC - Midtown
        type="restaurant",
        rating=4.9,
        price=4,
        tags=["french", "seafood", "fine-dining"],
    )

    await Location.create(
        name="Shake Shack",
        coordinates=(40.7792, -73.9759),  # NYC - Upper East Side
        type="restaurant",
        rating=4.3,
        price=2,
        tags=["burgers", "shakes", "casual"],
    )

    # Create some parks
    await Location.create(
        name="Central Park",
        coordinates=(40.7829, -73.9654),
        type="park",
        rating=4.8,
        tags=["outdoors", "recreation", "landmark"],
    )

    await Location.create(
        name="Washington Square Park",
        coordinates=(40.7308, -73.9974),
        type="park",
        rating=4.6,
        tags=["outdoors", "recreation", "historic"],
    )

    # Create some stores
    await Location.create(
        name="Macy's Herald Square",
        coordinates=(40.7508, -73.9895),
        type="store",
        rating=4.2,
        price=3,
        tags=["shopping", "department-store", "clothing"],
    )

    await Location.create(
        name="Apple Fifth Avenue",
        coordinates=(40.7638, -73.9729),
        type="store",
        rating=4.7,
        price=4,
        tags=["shopping", "electronics", "luxury"],
    )


async def demonstrate_queries():
    """Show different query patterns."""
    print("\nBasic Filtering:")
    # Find all high-rated locations (4.5+ stars)
    high_rated = await Location.find({"context.rating": {"$gte": 4.5}})
    print("\nHigh-rated locations (4.5+ stars):")
    for loc in high_rated:
        print(f"  {loc.name}: {loc.rating} stars")

    # Find affordable restaurants
    affordable = await Location.find(
        {"context.type": "restaurant", "context.price": {"$lte": 2}}
    )
    print("\nAffordable restaurants ($ or $$):")
    for loc in affordable:
        print(f"  {loc.name}: {'$' * loc.price}")

    print("\nComplex Queries:")
    # Find locations matching complex criteria
    luxury_spots = await Location.find(
        {
            "$and": [
                {"context.price": {"$gte": 3}},
                {"context.rating": {"$gte": 4.0}},
                {"context.tags": {"$in": ["luxury", "fine-dining"]}},
            ]
        }
    )
    print("\nLuxury locations (expensive & highly rated):")
    for loc in luxury_spots:
        print(f"  {loc.name}: {'$' * loc.price}, {loc.rating} stars")

    # Spatial query - find locations near Times Square
    times_square = (40.7580, -73.9855)
    nearby = await Location.find(
        {
            "context.coordinates": {
                "$near": times_square,
                "$maxDistance": 0.02,  # Roughly 2km
            }
        }
    )
    print("\nLocations near Times Square:")
    for loc in nearby:
        print(f"  {loc.name}")

    print("\nPagination Example:")
    # Use ObjectPager for paginated results
    pager = ObjectPager(
        Location,
        page_size=2,
        filters={"context.rating": {"$gte": 4.0}},
        order_by="rating",
        order_direction="desc",
    )

    # Only fetch first 3 pages as example
    for page_num in range(1, 4):
        locations = await pager.get_page(page_num)
        print(f"\nPage {page_num}:")
        if not locations:
            print("  No more locations")
            break
        for loc in locations:
            print(f"  {loc.name}: {loc.rating} stars")


async def cleanup_locations():
    """Clean up any existing locations from previous runs."""
    all_locations = await Location.all()
    for loc in all_locations:
        await loc.delete()


async def main():
    """Run the example."""
    print("Cleaning up previous data...")
    await cleanup_locations()

    print("\nCreating sample locations...")
    await create_sample_locations()

    print("\nDemonstrating different query patterns...")
    await demonstrate_queries()


if __name__ == "__main__":
    asyncio.run(main())
