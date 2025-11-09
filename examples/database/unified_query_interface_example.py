#!/usr/bin/env python3
"""
Unified MongoDB-style Query Interface Example

Demonstrates how the same MongoDB-style queries work consistently
across different database backends (JSON, MongoDB, custom databases).
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add the current project to the Python path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

from jvspatial.core import GraphContext, Node
from jvspatial.db import Database, create_database
from jvspatial.db.query import QueryBuilder, QueryEngine, query


# Custom database for testing query compatibility
class InMemoryDatabase(Database):
    def __init__(self, name: str = "memory"):
        self.name = name
        self._data: Dict[str, Any] = {}
        print(f"🔧 Created {name} database")

    async def clean(self) -> None:
        pass

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        key = f"{collection}:{data['id']}"
        self._data[key] = data.copy()
        return data

    async def get(self, collection: str, id: str):
        key = f"{collection}:{id}"
        return self._data.get(key)

    async def delete(self, collection: str, id: str) -> None:
        key = f"{collection}:{id}"
        self._data.pop(key, None)

    async def find(self, collection: str, query: Dict[str, Any]):
        """Use the standardized query matcher for custom databases."""
        results = []
        prefix = f"{collection}:"

        for key, doc in self._data.items():
            if key.startswith(prefix):
                # Use the unified MongoDB-style query engine
                if QueryEngine.match(doc, query):
                    results.append(doc)

        return results


def memory_configurator(kwargs):
    name = kwargs.get("name", "memory")
    return InMemoryDatabase(name)


class Product(Node):
    name: str = ""
    price: float = 0.0
    category: str = ""
    tags: List[str] = []
    in_stock: bool = True
    rating: float = 0.0


async def demonstrate_unified_queries():
    """Demonstrate MongoDB-style queries across different databases."""

    print("🔍 Unified MongoDB-style Query Interface Demo")
    print("=" * 60)

    # Create different database instances
    databases = {
        "JSON": create_database("json", base_path="temp_query_demo"),
        "Memory": InMemoryDatabase(name="QueryDemo"),
    }

    # Add MongoDB if available
    try:
        mongo_db = create_database("mongodb", db_name="query_demo_test")
        # Test the connection by attempting a simple operation
        await mongo_db.count("test")
        databases["MongoDB"] = mongo_db
    except Exception as e:
        print(f"⚠️  MongoDB not available ({type(e).__name__}), skipping MongoDB tests")

    print(f"\n🗄️  Testing with {len(databases)} database types:")
    for name in databases.keys():
        print(f"  • {name}")

    # Sample data
    sample_products = [
        {
            "name": "Laptop Pro",
            "price": 1299.99,
            "category": "electronics",
            "tags": ["computer", "professional"],
            "in_stock": True,
            "rating": 4.8,
        },
        {
            "name": "Wireless Mouse",
            "price": 29.99,
            "category": "electronics",
            "tags": ["computer", "wireless"],
            "in_stock": True,
            "rating": 4.2,
        },
        {
            "name": "Coffee Maker",
            "price": 89.99,
            "category": "kitchen",
            "tags": ["appliance", "coffee"],
            "in_stock": False,
            "rating": 4.5,
        },
        {
            "name": "Running Shoes",
            "price": 129.99,
            "category": "sports",
            "tags": ["footwear", "running"],
            "in_stock": True,
            "rating": 4.6,
        },
        {
            "name": "Bluetooth Speaker",
            "price": 79.99,
            "category": "electronics",
            "tags": ["audio", "bluetooth", "portable"],
            "in_stock": True,
            "rating": 4.3,
        },
        {
            "name": "Yoga Mat",
            "price": 39.99,
            "category": "sports",
            "tags": ["fitness", "yoga"],
            "in_stock": True,
            "rating": 4.7,
        },
        {
            "name": "Smart Watch",
            "price": 299.99,
            "category": "electronics",
            "tags": ["wearable", "smart", "health"],
            "in_stock": False,
            "rating": 4.1,
        },
    ]

    # Insert sample data into all databases
    print(f"\n📝 Inserting {len(sample_products)} sample products...")
    for db_name, db in databases.items():
        ctx = GraphContext(database=db)
        for i, product_data in enumerate(sample_products):
            await ctx.create(Product, **product_data)
        print(f"  ✅ {db_name}: {len(sample_products)} products inserted")

    # Test Query 1: Simple equality - query the actual Node structure
    print(f"\n1️⃣  Simple Equality Query")
    print(f'Query: {{"context.category": "electronics"}}')
    simple_query = {"context.category": "electronics"}

    for db_name, db in databases.items():
        results = await db.find("node", simple_query)
        print(f"  {db_name}: {len(results)} results")

    # Test Query 2: Comparison operators
    print(f"\n2️⃣  Comparison Operators")
    print(f'Query: {{"context.price": {{"$gt": 100, "$lt": 200}}}}')
    comparison_query = {"context.price": {"$gt": 100, "$lt": 200}}

    for db_name, db in databases.items():
        results = await db.find("node", comparison_query)
        print(f"  {db_name}: {len(results)} results")
        if results:
            print(f"    Examples: {[r.get('name') for r in results[:2]]}")

    # Test Query 3: Array operations
    print(f"\n3️⃣  Array Operations")
    print(f'Query: {{"context.tags": {{"$in": ["computer", "fitness"]}}}}')
    array_query = {"context.tags": {"$in": ["computer", "fitness"]}}

    for db_name, db in databases.items():
        results = await db.find("node", array_query)
        print(f"  {db_name}: {len(results)} results")
        if results:
            print(f"    Examples: {[r.get('name') for r in results[:2]]}")

    # Test Query 4: Logical operators
    print(f"\n4️⃣  Logical Operators (AND)")
    print(
        f'Query: {{"$and": [{{"context.category": "electronics"}}, {{"context.price": {{"$lt": 100}}}}]}}'
    )
    logical_query = {
        "$and": [{"context.category": "electronics"}, {"context.price": {"$lt": 100}}]
    }

    for db_name, db in databases.items():
        results = await db.find("node", logical_query)
        print(f"  {db_name}: {len(results)} results")
        if results:
            print(f"    Examples: {[r.get('name') for r in results[:2]]}")

    # Test Query 5: OR operations
    print(f"\n5️⃣  Logical Operators (OR)")
    print(
        f'Query: {{"$or": [{{"context.category": "sports"}}, {{"context.price": {{"$gt": 1000}}}}]}}'
    )
    or_query = {
        "$or": [{"context.category": "sports"}, {"context.price": {"$gt": 1000}}]
    }

    for db_name, db in databases.items():
        results = await db.find("node", or_query)
        print(f"  {db_name}: {len(results)} results")
        if results:
            print(f"    Examples: {[r.get('name') for r in results[:2]]}")

    # Test Query 6: Existence checks
    print(f"\n6️⃣  Field Existence")
    print(
        f'Query: {{"context.rating": {{"$exists": true}}, "context.in_stock": false}}'
    )
    existence_query = {"context.rating": {"$exists": True}, "context.in_stock": False}

    for db_name, db in databases.items():
        results = await db.find("node", existence_query)
        print(f"  {db_name}: {len(results)} results")
        if results:
            print(f"    Examples: {[r.get('name') for r in results[:2]]}")

    # Test Query 7: Array size
    print(f"\n7️⃣  Array Size")
    print(f'Query: {{"context.tags": {{"$size": 3}}}}')
    size_query = {"context.tags": {"$size": 3}}

    for db_name, db in databases.items():
        results = await db.find("node", size_query)
        print(f"  {db_name}: {len(results)} results")
        if results:
            print(f"    Examples: {[r.get('name') for r in results[:2]]}")

    # Test enhanced query methods
    print(f"\n8️⃣  Enhanced Query Methods")

    print(f"\n  📊 Count Operations:")
    count_query = {"context.category": "electronics"}
    for db_name, db in databases.items():
        count = await db.count("node", count_query)
        print(f"    {db_name}: {count} electronics")

    print(f"\n  🔍 Find One:")
    for db_name, db in databases.items():
        result = await db.find_one("node", {"context.price": {"$gt": 1000}})
        if result:
            context = result.get("context", {})
            print(f"    {db_name}: {context.get('name')} (${context.get('price')})")
        else:
            print(f"    {db_name}: No expensive items found")

    print(f"\n  🎯 Distinct Values:")
    for db_name, db in databases.items():
        # Get all records and extract unique category values
        all_records = await db.find("node", {})
        categories = set()
        for record in all_records:
            context = record.get("context", {})
            category = context.get("category")
            if category:
                categories.add(category)
        print(f"    {db_name}: {len(categories)} categories: {sorted(categories)}")

    # Test Query Builder
    print(f"\n9️⃣  Query Builder Usage")

    # Build complex query programmatically
    builder = query()
    builder.field("context.category").eq("electronics")
    builder.field("context.price").gte(50)
    builder.field("context.price").lte(150)
    builder.field("context.in_stock").eq(True)
    builder_query = builder.build()

    print(f"Built query: {builder_query}")

    for db_name, db in databases.items():
        results = await db.find("node", builder_query)
        print(f"  {db_name}: {len(results)} results")
        if results:
            print(
                f"    Examples: {[r.get('context', {}).get('name') for r in results[:2]]}"
            )

    # Test update operations
    print(f"\n🔄 Update Operations:")

    # Update price of all electronics
    update_query = {"context.category": "electronics"}
    update_ops = {"$inc": {"context.price": 10}}  # Increase price by $10

    for db_name, db in databases.items():
        # update_many is not available in the Database interface
        # Instead, find records and update them individually
        records_to_update = await db.find("node", update_query)
        modified_count = 0
        for record in records_to_update:
            # Update the record with $inc operation
            context = record.get("context", {})
            if "price" in context:
                context["price"] = context.get("price", 0) + update_ops.get(
                    "$inc", {}
                ).get("context.price", 10)
                record["context"] = context
                await db.save("node", record)
                modified_count += 1
        print(f"  {db_name}: Modified {modified_count} electronics")

    # Verify updates worked
    print(f"\n  📋 Verification (electronics after price increase):")
    for db_name, db in databases.items():
        electronics = await db.find("node", {"context.category": "electronics"})
        if electronics:
            avg_price = sum(
                item.get("context", {}).get("price", 0) for item in electronics
            ) / len(electronics)
            print(f"    {db_name}: Average electronics price: ${avg_price:.2f}")

    # Test delete operations
    print(f"\n🗑️  Delete Operations:")

    # Delete out-of-stock items
    delete_query = {"context.in_stock": False}

    for db_name, db in databases.items():
        # delete_many is not available in the Database interface
        # Instead, find records and delete them individually
        records_to_delete = await db.find("node", delete_query)
        deleted_count = 0
        for record in records_to_delete:
            record_id = record.get("_id") or record.get("id")
            if record_id:
                await db.delete("node", record_id)
                deleted_count += 1
        print(f"  {db_name}: Deleted {deleted_count} out-of-stock items")

    # Final count
    print(f"\n📊 Final Counts:")
    for db_name, db in databases.items():
        total = await db.count("node")
        print(f"  {db_name}: {total} total products remaining")

    print(f"\n✅ Unified Query Interface Demo Complete!")
    print(f"\n🎯 Key Benefits:")
    print(f"  • Same MongoDB-style queries work on all databases")
    print(f"  • Native optimization where available (MongoDB)")
    print(f"  • Standardized query parsing for custom databases")
    print(f"  • Comprehensive operator support")
    print(f"  • Enhanced methods: find_one, count, distinct, update, delete")
    print(f"  • Programmatic query builder")

    # Cleanup
    import shutil

    temp_path = Path("temp_query_demo")
    if temp_path.exists():
        shutil.rmtree(temp_path)
        print(f"\n🧹 Cleaned up temporary files")


if __name__ == "__main__":
    asyncio.run(demonstrate_unified_queries())
