"""
Demonstrates CRUD operations with MongoDB-style queries and unified database interface.
Shows how to use the unified query interface across different database backends.
"""

import asyncio
import os

from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Edge, Node
from jvspatial.db import get_database


class City(Node):
    """City entity with common properties"""

    name: str = ""
    population: int = 0
    latitude: float = 0.0
    longitude: float = 0.0


async def crud_operations():
    """Execute full CRUD lifecycle with MongoDB-style queries"""

    # Get database using the unified factory system
    db = get_database()  # Uses environment variable or default
    ctx = GraphContext(database=db)

    print(f"🗄️  Using database: {type(db).__name__}")

    # CREATE: Entity-centric creation (recommended syntax)
    print("\n📝 CREATE Operations:")
    city = await City.create(
        name="Metropolis", population=1000000, latitude=40.7128, longitude=-74.0060
    )
    print(f"Created city: {city.name} ({city.id})")

    # Create multiple cities for query examples
    cities_data = [
        {
            "name": "New York",
            "population": 8400000,
            "latitude": 40.7128,
            "longitude": -74.0060,
        },
        {
            "name": "Los Angeles",
            "population": 3900000,
            "latitude": 34.0522,
            "longitude": -118.2437,
        },
        {
            "name": "Chicago",
            "population": 2700000,
            "latitude": 41.8781,
            "longitude": -87.6298,
        },
        {
            "name": "Houston",
            "population": 2300000,
            "latitude": 29.7604,
            "longitude": -95.3698,
        },
    ]

    created_cities = []
    for city_data in cities_data:
        city = await City.create(**city_data)
        created_cities.append(city)
        print(f"  Created: {city.name}")

    # READ: Entity-centric retrieval
    print(f"\n📖 READ Operations:")
    retrieved = await City.get(city.id)
    print(f"Retrieved by ID: {retrieved.name} (pop: {retrieved.population:,})")

    # READ: MongoDB-style queries using the Object base class methods
    print(f"\n🔍 MongoDB-style Query Operations:")

    # Find all cities
    all_cities = await City.find()
    print(f"Total cities found: {len(all_cities)}")

    # Find cities by population range
    large_cities = await City.find({"context.population": {"$gte": 3000000}})
    print(f"Large cities (>= 3M): {[c.name for c in large_cities]}")

    # Find cities using logical operators
    west_coast_cities = await City.find(
        {
            "$and": [
                {"context.longitude": {"$lt": -100}},
                {"context.latitude": {"$gte": 30}},
            ]
        }
    )
    print(f"West coast cities: {[c.name for c in west_coast_cities]}")

    # Find cities using convenience method
    chicago_cities = await City.find_by(name="Chicago")
    print(f"Cities named Chicago: {[c.name for c in chicago_cities]}")

    # Count operations
    total_count = await City.count()
    large_count = await City.count({"context.population": {"$gte": 3000000}})
    print(f"Total cities: {total_count}, Large cities: {large_count}")

    # Find one operation
    largest_city = await City.find_one({"context.population": {"$gte": 8000000}})
    if largest_city:
        print(f"Largest city found: {largest_city.name} ({largest_city.population:,})")

    # Distinct values
    distinct_names = await City.distinct("name")
    print(f"Distinct city names: {distinct_names}")

    # UPDATE: Using database-level updates
    print(f"\n✏️  UPDATE Operations:")

    # Update using the enhanced database methods
    update_result = await db.update_many(
        "node",
        {"name": "City", "context.population": {"$lt": 3000000}},
        {"$inc": {"context.population": 100000}},  # Increase small cities by 100k
    )
    print(f"Updated {update_result.get('modified_count', 0)} smaller cities")

    # Traditional object update
    if retrieved:
        retrieved.latitude = 40.7500  # Slight adjustment
        await retrieved.save()
        print(f"Updated {retrieved.name} coordinates")

    # DELETE: Using database-level deletes
    print(f"\n🗑️  DELETE Operations:")

    # Delete using query
    delete_result = await db.delete_many(
        "node", {"name": "City", "context.population": {"$lt": 2500000}}
    )
    print(f"Deleted {delete_result.get('deleted_count', 0)} smaller cities")

    # Entity-centric delete
    if retrieved:
        await retrieved.delete()  # Delete via the entity itself
        print(f"Deleted {retrieved.name}")

    # Final verification
    print(f"\n🔍 Final Verification:")
    remaining_cities = await City.find()
    print(f"Remaining cities: {[c.name for c in remaining_cities]}")

    # Verify deleted city is gone
    deleted_check = await City.get(city.id)
    print(f"Original city exists: {deleted_check is not None}")


if __name__ == "__main__":
    asyncio.run(crud_operations())
