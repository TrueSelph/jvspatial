"""Database Error Handling Example

Demonstrates database-related error handling in jvspatial, including:
- Connection errors
- Query errors
- Transaction errors
- Fallback strategies
"""

import asyncio
import os
from typing import Any, Dict, Optional

from jvspatial.core import GraphContext, Node
from jvspatial.db.factory import get_database
from jvspatial.exceptions import (
    ConfigurationError,
    ConnectionError,
    DatabaseError,
    EntityNotFoundError,
    InvalidConfigurationError,
    QueryError,
    ValidationError,
)


# Define example entity
class Product(Node):
    """Product entity for database operations."""

    name: str = ""
    price: float = 0.0
    stock: int = 0
    category: str = ""
    active: bool = True


def setup_database_with_fallback() -> Optional[str]:
    """Attempt to set up database with fallback options."""
    print("\n🔌 Setting up database connection:")

    try:
        # Try MongoDB first (will fail if not configured)
        os.environ["JVSPATIAL_DB_TYPE"] = "mongodb"
        os.environ["JVSPATIAL_MONGODB_URI"] = "invalid://connection"
        db = get_database("mongodb")
        print("✅ Connected to MongoDB")
        return "mongodb"

    except InvalidConfigurationError as e:
        print(f"❌ MongoDB configuration invalid: {e.message}")
        print(f"  • Config key: {e.config_key}")
        print(f"  • Value: {e.config_value}")

        # Fall back to JSON database
        try:
            os.environ["JVSPATIAL_DB_TYPE"] = "json"
            os.environ["JVSPATIAL_JSONDB_PATH"] = "./jvdb"
            db = get_database("json")
            print("✅ Fallback: Connected to JSON database")
            return "json"

        except ConfigurationError as e:
            print(f"❌ JSON database configuration failed: {e.message}")
            return None


async def demonstrate_query_error_handling():
    """Demonstrate handling of query-related errors."""
    print("\n🔍 Demonstrating query error handling:")

    try:
        # Try invalid query
        invalid_query = {"$invalid": "operator"}
        products = await Product.find(invalid_query)

    except QueryError as e:
        print(f"❌ Query failed: {e.message}")
        print(f"  • Invalid query: {e.query}")

        # Attempt simpler query as fallback
        try:
            print("\n🔄 Attempting fallback query:")
            products = await Product.find({"context.active": True})
            print(f"✅ Fallback query succeeded: found {len(products)} products")

        except DatabaseError as e:
            print(f"❌ Fallback query failed: {e.message}")


async def demonstrate_transaction_safety():
    """Demonstrate safe transaction handling."""
    print("\n💾 Demonstrating transaction safety:")

    async def update_product_safely(product_id: str, updates: Dict[str, Any]):
        """Safe product update with error handling."""
        try:
            product = await Product.get(product_id)
            if product is None:
                raise EntityNotFoundError(
                    entity_type="Product",
                    entity_id=product_id,
                    details={"message": "Product not found"},
                )

            # Store original values for rollback
            original_values = {
                "price": product.price,
                "stock": product.stock,
            }

            # Apply updates
            product.price = updates.get("price", product.price)
            product.stock = updates.get("stock", product.stock)

            # Validate and save
            await product.save()
            print(f"✅ Updated product {product.name}")

        except EntityNotFoundError as e:
            print(f"❌ Product not found: {e.message}")

        except ValidationError as e:
            print(f"❌ Validation failed: {e.message}")
            # Rollback changes
            if "product" in locals() and product is not None:
                product.price = original_values["price"]
                product.stock = original_values["stock"]
                await product.save()
                print("↩️  Rolled back changes")

        except DatabaseError as e:
            print(f"❌ Database error: {e.message}")
            if e.details:
                print(f"  • Details: {e.details}")


async def demonstrate_connection_handling():
    """Demonstrate database connection error handling."""
    print("\n🔌 Demonstrating connection handling:")

    try:
        # Force a connection error
        os.environ["JVSPATIAL_MONGODB_URI"] = "mongodb://invalid:27017"
        ctx = GraphContext()
        await ctx.connect()

    except ConnectionError as e:
        print(f"❌ Connection failed: {e.message}")
        print(f"  • Database type: {e.database_type}")

        # Implement retry logic
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                print(f"\n🔄 Retry attempt {retry_count + 1}/{max_retries}")
                # Use different connection settings
                os.environ["JVSPATIAL_DB_TYPE"] = "json"
                ctx = GraphContext()
                await ctx.connect()
                print("✅ Connected successfully using fallback")
                break

            except DatabaseError as e:
                retry_count += 1
                if retry_count == max_retries:
                    print(f"❌ All retry attempts failed: {e.message}")


async def main():
    """Run database error handling demonstrations."""
    print("🚀 Database Error Handling Example")
    print("================================")

    try:
        # Try to set up database
        db_type = setup_database_with_fallback()
        if not db_type:
            print("❌ Could not establish database connection")
            return

        # Run demonstrations
        await demonstrate_connection_handling()
        await demonstrate_query_error_handling()
        await demonstrate_transaction_safety()

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

    print("\n✨ Example completed!")


if __name__ == "__main__":
    asyncio.run(main())
