#!/usr/bin/env python3
"""
Modern Query Interface Example

Demonstrates the unified MongoDB-style query interface in jvspatial
using clean, entity-centric syntax. Works across all database backends.
"""

import asyncio
import sys
from pathlib import Path
from typing import List

# Add the current project to the Python path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

from jvspatial.core import Node
from jvspatial.db import get_database, query


class User(Node):
    """User entity with various properties for query examples."""

    name: str = ""
    email: str = ""
    age: int = 0
    active: bool = True
    roles: List[str] = []
    department: str = ""


class Product(Node):
    """Product entity for showcasing different query patterns."""

    name: str = ""
    price: float = 0.0
    category: str = ""
    in_stock: bool = True
    tags: List[str] = []
    rating: float = 0.0


async def demonstrate_modern_queries():
    """Demonstrate modern MongoDB-style querying with entity-centric syntax."""

    print("🚀 Modern Query Interface - Entity-Centric Syntax")
    print("=" * 60)

    # Set up database - works with JSON, MongoDB, or custom databases
    db = get_database()  # Uses environment variable or default
    print(f"🗄️  Using database: {type(db).__name__}")

    # CREATE: Clean entity creation
    print("\n📝 CREATE - Entity-Centric Creation")
    print("-" * 40)

    print("✅ Creating users...")
    users = [
        await User.create(
            name="Alice Johnson",
            email="alice@company.com",
            age=28,
            active=True,
            roles=["developer", "team_lead"],
            department="engineering",
        ),
        await User.create(
            name="Bob Smith",
            email="bob@company.com",
            age=35,
            active=True,
            roles=["developer"],
            department="engineering",
        ),
        await User.create(
            name="Carol Davis",
            email="carol@company.com",
            age=42,
            active=False,
            roles=["manager"],
            department="engineering",
        ),
        await User.create(
            name="David Wilson",
            email="david@company.com",
            age=31,
            active=True,
            roles=["designer"],
            department="design",
        ),
        await User.create(
            name="Eve Brown",
            email="eve@company.com",
            age=26,
            active=True,
            roles=["analyst"],
            department="marketing",
        ),
    ]
    print(f"Created {len(users)} users")

    print("✅ Creating products...")
    products = [
        await Product.create(
            name="Pro Laptop",
            price=1299.99,
            category="electronics",
            in_stock=True,
            tags=["computer", "professional"],
            rating=4.8,
        ),
        await Product.create(
            name="Wireless Mouse",
            price=79.99,
            category="electronics",
            in_stock=True,
            tags=["computer", "wireless"],
            rating=4.5,
        ),
        await Product.create(
            name="Office Chair",
            price=299.99,
            category="furniture",
            in_stock=False,
            tags=["office", "ergonomic"],
            rating=4.2,
        ),
        await Product.create(
            name="Standing Desk",
            price=599.99,
            category="furniture",
            in_stock=True,
            tags=["office", "adjustable"],
            rating=4.7,
        ),
        await Product.create(
            name="Programming Book",
            price=49.99,
            category="books",
            in_stock=True,
            tags=["education"],
            rating=4.6,
        ),
    ]
    print(f"Created {len(products)} products")

    # READ: Basic retrieval patterns
    print("\n📖 READ - Simple Retrieval")
    print("-" * 40)

    # Get by ID
    alice = users[0]
    retrieved_user = await User.get(alice.id)
    print(f"Retrieved by ID: {retrieved_user.name}")

    # Find all
    all_users = await User.find()
    print(f"Total users: {len(all_users)}")

    # Find with simple criteria
    active_users = await User.find_by(active=True)
    print(f"Active users: {[u.name for u in active_users]}")

    # MONGODB-STYLE QUERIES
    print("\n🔍 MONGODB-STYLE QUERIES")
    print("-" * 40)

    # Comparison operators
    print("📊 Comparison Operators:")
    seniors = await User.find({"context.age": {"$gte": 35}})
    print(f"  Senior employees (>=35): {[u.name for u in seniors]}")

    affordable = await Product.find({"context.price": {"$lte": 100}})
    print(f"  Affordable products (<=100): {[p.name for p in affordable]}")

    # Range queries
    print("📈 Range Queries:")
    mid_price = await Product.find({"context.price": {"$gte": 200, "$lte": 800}})
    print(f"  Mid-range products ($200-$800): {[p.name for p in mid_price]}")

    # Logical operators
    print("🧠 Logical Operators:")
    active_engineers = await User.find(
        {"$and": [{"context.active": True}, {"context.department": "engineering"}]}
    )
    print(f"  Active engineers: {[u.name for u in active_engineers]}")

    creative_roles = await User.find(
        {"$or": [{"context.department": "design"}, {"context.department": "marketing"}]}
    )
    print(f"  Creative departments: {[u.name for u in creative_roles]}")

    # Array operations
    print("📋 Array Operations:")
    tech_products = await Product.find(
        {"context.tags": {"$in": ["computer", "professional"]}}
    )
    print(f"  Tech products: {[p.name for p in tech_products]}")

    multi_tag_products = await Product.find({"context.tags": {"$size": 2}})
    print(f"  Products with exactly 2 tags: {[p.name for p in multi_tag_products]}")

    # COUNTING AND AGGREGATION
    print("\n📊 COUNTING & AGGREGATION")
    print("-" * 40)

    total_users = await User.count()
    active_count = await User.count({"context.active": True})
    print(f"Users: {total_users} total, {active_count} active")

    expensive_product = await Product.find_one({"context.price": {"$gte": 1000}})
    print(
        f"Most expensive product: {expensive_product.name if expensive_product else 'None'}"
    )

    departments = await User.distinct("department")
    categories = await Product.distinct("category")
    print(f"Departments: {departments}")
    print(f"Product categories: {categories}")

    # QUERY BUILDER
    print("\n🏗️  QUERY BUILDER")
    print("-" * 40)

    # Build complex queries programmatically
    complex_query = (
        query()
        .field("context.category")
        .eq("electronics")
        .field("context.price")
        .gte(50)
        .field("context.in_stock")
        .eq(True)
        .build()
    )

    electronics = await Product.find(complex_query)
    print(f"In-stock electronics (>=$50): {[p.name for p in electronics]}")

    # UPDATE: Entity-centric updates
    print("\n✏️  UPDATE - Entity Updates")
    print("-" * 40)

    # Update individual entity
    if retrieved_user:
        retrieved_user.age += 1  # Birthday!
        await retrieved_user.save()
        print(f"Updated {retrieved_user.name}'s age to {retrieved_user.age}")

    # Database-level bulk updates
    update_result = await db.update_many(
        "node",
        {"name": "Product", "context.category": "electronics"},
        {"$mul": {"context.price": 0.95}},  # 5% discount
    )
    print(f"Applied discount to {update_result.get('modified_count', 0)} electronics")

    # DELETE: Entity-centric deletion
    print("\n🗑️  DELETE - Entity Deletion")
    print("-" * 40)

    # Delete individual entity
    out_of_stock = await Product.find_one({"context.in_stock": False})
    if out_of_stock:
        print(f"Deleting out-of-stock product: {out_of_stock.name}")
        await out_of_stock.delete()

    # Database-level bulk delete
    delete_result = await db.delete_many(
        "node", {"name": "User", "context.active": False}
    )
    print(f"Removed {delete_result.get('deleted_count', 0)} inactive users")

    # ADVANCED PATTERNS
    print("\n🚀 ADVANCED PATTERNS")
    print("-" * 40)

    # Complex nested queries
    complex_users = await User.find(
        {
            "$or": [
                {
                    "$and": [
                        {"context.department": "engineering"},
                        {"context.age": {"$gte": 30}},
                    ]
                },
                {"context.roles": {"$in": ["analyst", "designer"]}},
            ]
        }
    )
    print(f"Complex query results: {[u.name for u in complex_users]}")

    # Regular expressions
    johnson_users = await User.find(
        {"context.name": {"$regex": "Johnson", "$options": "i"}}
    )
    print(f"Users with 'Johnson': {[u.name for u in johnson_users]}")

    # Field existence
    rated_products = await Product.find({"context.rating": {"$exists": True}})
    print(f"Products with ratings: {len(rated_products)}")

    # FINAL VERIFICATION
    print("\n✅ FINAL STATUS")
    print("-" * 40)

    remaining_users = await User.count()
    remaining_products = await Product.count()
    print(f"Final count - Users: {remaining_users}, Products: {remaining_products}")

    print("\n🎯 KEY BENEFITS")
    print("-" * 40)
    benefits = [
        "✨ Clean, entity-centric syntax: User.create(), user.save(), user.delete()",
        "🔍 Rich MongoDB-style queries: $gte, $and, $in, $regex, etc.",
        "🗄️  Works across JSON, MongoDB, and custom databases seamlessly",
        "⚡ Efficient operations: count(), find_one(), distinct(), bulk updates",
        "🏗️  Programmatic query building with fluent interface",
        "🧪 Same code works for development, testing, and production databases",
    ]

    for benefit in benefits:
        print(f"  {benefit}")

    print(f"\n🚀 Jvspatial Query Interface Demo Complete!")


if __name__ == "__main__":
    asyncio.run(demonstrate_modern_queries())
