#!/usr/bin/env python3
"""
Object Pagination Demo

Demonstrates the ObjectPager functionality for paginating through different
types of objects including nodes, edges, and custom objects.
"""

import asyncio
import sys
from pathlib import Path

# Add the current project to the Python path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

from jvspatial.core import (
    Edge,
    Node,
    Object,
    ObjectPager,
    paginate_by_field,
    paginate_objects,
)


class Document(Object):
    """Custom object for demonstration."""

    title: str = "Untitled"
    content: str = ""
    category: str = "general"


class City(Node):
    """Node representing a city."""

    name: str = "Unknown"
    population: int = 0
    country: str = "Unknown"


class Highway(Edge):
    """Edge representing a highway connection."""

    name: str = "Unnamed Highway"
    lanes: int = 2
    speed_limit: int = 65


async def demo_object_pagination():
    """Demonstrate ObjectPager with different object types."""

    print("🚀 Object Pagination Demo")
    print("=" * 50)

    # Demo 1: Simple object pagination
    print("\n📄 1. Document Pagination")
    print("-" * 25)

    # Create a pager for Documents
    doc_pager = ObjectPager(Document, page_size=10, filters={"category": "technical"})

    print(f"Created Document pager: {doc_pager}")
    print("✓ Document pager supports filtering by category")

    # Demo 2: Node pagination with ObjectPager
    print("\n🏙️  2. City (Node) Pagination")
    print("-" * 30)

    # Create a pager for Cities (which are Nodes)
    city_pager = ObjectPager(
        City,
        page_size=25,
        filters={"population": {"$gt": 100000}},
        order_by="population",
        order_direction="desc",
    )

    print(f"Created City pager: {city_pager}")
    print("✓ City pager supports population filtering and ordering")

    # Demo 3: Edge pagination
    print("\n🛣️  3. Highway (Edge) Pagination")
    print("-" * 32)

    highway_pager = ObjectPager(
        Highway, page_size=15, order_by="speed_limit", order_direction="desc"
    )

    print(f"Created Highway pager: {highway_pager}")
    print("✓ Highway pager supports ordering by speed limit")

    # Demo 4: Using helper functions
    print("\n🔧 4. Pagination Helper Functions")
    print("-" * 35)

    print("Available helper functions:")
    print("  • paginate_objects() - Simple object pagination")
    print("  • paginate_by_field() - Field-based pagination with ordering")

    # Example usage patterns (without actual database operations)
    print("\n📋 Usage Examples:")
    print("  cities = await paginate_objects(City, page=1, page_size=20)")
    print("  docs = await paginate_by_field(Document, 'title', page_size=10)")
    print("  roads = await ObjectPager(Highway).get_page()")

    # Demo 5: Show flexibility
    print("\n✨ 5. ObjectPager Flexibility")
    print("-" * 32)

    object_types = [
        (Object, "Base objects"),
        (Node, "Graph nodes"),
        (Edge, "Graph edges"),
        (City, "City nodes"),
        (Highway, "Highway edges"),
        (Document, "Custom objects"),
    ]

    for obj_type, description in object_types:
        pager = ObjectPager(obj_type, page_size=20)
        print(f"✓ {description:15} -> {pager}")

    # Demo 6: Pager properties and methods
    print("\n⚙️  6. Pager Properties & Methods")
    print("-" * 35)

    demo_pager = ObjectPager(City, page_size=50)

    print("Available methods:")
    print(f"  • get_page(1)        -> Get specific page")
    print(f"  • next_page()        -> Get next page")
    print(f"  • previous_page()    -> Get previous page")
    print(f"  • has_next_page()    -> Check if next page exists")
    print(f"  • has_previous_page()-> Check if previous page exists")
    print(f"  • to_dict()          -> Get pagination metadata")

    print("\nAvailable properties:")
    print(f"  • current_page: {demo_pager.current_page}")
    print(f"  • page_size:    {demo_pager.page_size}")
    print(f"  • total_pages:  {demo_pager.total_pages}")
    print(f"  • total_items:  {demo_pager.total_items}")
    print(f"  • is_cached:    {demo_pager.is_cached}")

    print("\n🎯 Summary")
    print("-" * 15)
    print("ObjectPager provides unified pagination for:")
    print("  ✓ Base Object instances")
    print("  ✓ Node instances (including custom node types)")
    print("  ✓ Edge instances (including custom edge types)")
    print("  ✓ Any custom object inheriting from Object")
    print("  ✓ Database-level filtering and ordering")
    print("  ✓ Memory-efficient processing of large datasets")

    print("\n✅ Demo completed successfully!")


if __name__ == "__main__":
    asyncio.run(demo_object_pagination())
