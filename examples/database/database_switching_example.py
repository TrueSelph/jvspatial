#!/usr/bin/env python3
"""
Database Switching Example

Demonstrates various ways to dynamically switch databases in jvspatial:
1. Per-operation database switching
2. Context-based switching
3. Default context switching
4. Environment-based switching
5. Application lifecycle switching
"""

import asyncio
import os
from typing import Any, Dict

from jvspatial.core import Edge, GraphContext, Node, set_default_context
from jvspatial.db import Database


# Simple mock database for demonstration
class MockDatabase(Database):
    def __init__(self, name: str):
        self.name = name
        self._data: Dict[str, Any] = {}
        print(f"🔧 Created {name} database")

    async def clean(self) -> None:
        pass

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        key = f"{collection}:{data['id']}"
        self._data[key] = data
        print(f"💾 Saved to {self.name}: {key}")
        return data

    async def get(self, collection: str, id: str):
        key = f"{collection}:{id}"
        result = self._data.get(key)
        print(
            f"📖 Read from {self.name}: {key} -> {'found' if result else 'not found'}"
        )
        return result

    async def delete(self, collection: str, id: str) -> None:
        key = f"{collection}:{id}"
        self._data.pop(key, None)
        print(f"🗑️  Deleted from {self.name}: {key}")

    async def find(self, collection: str, query: Dict[str, Any]):
        results = []
        prefix = f"{collection}:"
        for key, doc in self._data.items():
            if key.startswith(prefix):
                results.append(doc)
        print(f"🔍 Found {len(results)} items in {self.name}")
        return results


class Person(Node):
    name: str = ""
    age: int = 0


async def demonstrate_database_switching():
    """Show different ways to switch databases dynamically."""

    print("🔀 Database Switching Demonstration")
    print("=" * 50)

    # Method 1: Per-Operation Database Switching
    print("\n1️⃣  Per-Operation Database Switching")
    print("-" * 40)

    # Create different database instances
    dev_db = MockDatabase(name="Development")
    test_db = MockDatabase(name="Testing")
    prod_db = MockDatabase(name="Production")

    # Use different databases for different operations
    dev_ctx = GraphContext(database=dev_db)
    test_ctx = GraphContext(database=test_db)
    prod_ctx = GraphContext(database=prod_db)

    # Set default context for entity-centric operations
    set_default_context(dev_ctx)
    alice_dev = await Person.create(name="Alice", age=30)

    set_default_context(test_ctx)
    alice_test = await Person.create(name="Alice", age=30)

    set_default_context(prod_ctx)
    alice_prod = await Person.create(name="Alice", age=30)

    print("✅ Same data operations on different databases")

    # Method 2: Context-Based Switching
    print("\n2️⃣  Context-Based Database Switching")
    print("-" * 40)

    async def process_user_data(user_id: str, environment: str):
        """Process user data in different environments."""
        if environment == "dev":
            ctx = GraphContext(database=dev_db)
        elif environment == "test":
            ctx = GraphContext(database=test_db)
        else:
            ctx = GraphContext(database=prod_db)

        # Set context for entity-centric operations
        set_default_context(ctx)

        # Same logic, different database
        person = await Person.get(user_id)
        if person:
            print(f"📊 Processing {person.name} in {environment} environment")
        return person

    # Process same user in different environments
    await process_user_data(alice_dev.id, "dev")
    await process_user_data(alice_test.id, "test")
    await process_user_data(alice_prod.id, "prod")

    # Method 3: Default Context Switching
    print("\n3️⃣  Default Context Switching")
    print("-" * 40)

    # Create a new default context
    default_db = MockDatabase(name="Default")
    default_ctx = GraphContext(database=default_db)
    set_default_context(default_ctx)

    # Entity-centric operations use the default context
    bob = await Person.create(name="Bob", age=25)
    print("✅ Created Bob using default context")

    # Method 4: Environment-Based Switching
    print("\n4️⃣  Environment-Based Database Switching")
    print("-" * 40)

    def get_database_for_environment():
        """Get database based on environment variables."""
        env = os.getenv("APP_ENV", "development")

        if env == "production":
            return MockDatabase(name="Production-ENV")
        elif env == "testing":
            return MockDatabase(name="Testing-ENV")
        else:
            return MockDatabase(name="Development-ENV")

    # Test different environments
    environments = ["development", "testing", "production"]

    for env in environments:
        os.environ["APP_ENV"] = env
        db = get_database_for_environment()
        ctx = GraphContext(database=db)
        set_default_context(ctx)

        charlie = await Person.create(name=f"Charlie-{env}", age=35)
        print(f"✅ Created Charlie in {env} environment")

    # Clean up environment
    if "APP_ENV" in os.environ:
        del os.environ["APP_ENV"]

    # Method 5: Application Lifecycle Switching
    print("\n5️⃣  Application Lifecycle Database Switching")
    print("-" * 40)

    class ApplicationManager:
        def __init__(self):
            self.current_db = None
            self.context = None

        async def initialize(self, database: Database):
            """Initialize with a specific database."""
            self.current_db = database
            self.context = GraphContext(database=self.current_db)
            set_default_context(self.context)
            print(
                f"🚀 Application initialized with {database.name if hasattr(database, 'name') else type(database).__name__}"
            )

        async def switch_database(self, database: Database):
            """Switch to a different database."""
            db_name = (
                database.name if hasattr(database, "name") else type(database).__name__
            )
            current_name = (
                self.current_db.name
                if hasattr(self.current_db, "name")
                else type(self.current_db).__name__
            )
            print(f"🔄 Switching from {current_name} to {db_name}")

            # Create new context
            new_context = GraphContext(database=database)

            # Optional: Migrate data (simplified example)
            await self._migrate_data(self.context, new_context)

            # Switch
            self.current_db = database
            self.context = new_context
            set_default_context(new_context)
            print("✅ Database switch completed")

        async def _migrate_data(self, old_ctx: GraphContext, new_ctx: GraphContext):
            """Simplified data migration between databases."""
            # In a real application, you'd implement proper migration logic
            print("📦 Migrating data between databases...")
            # This is just for demonstration - real migration would be more complex

    # Demonstrate application lifecycle switching
    app = ApplicationManager()

    await app.initialize(MockDatabase(name="Initial-DB"))

    # Create some data using entity-centric operations
    initial_person = await Person.create(name="Diana", age=40)
    print(f"✅ Created Diana: {initial_person.id}")

    # Switch databases during runtime
    await app.switch_database(MockDatabase(name="New-DB"))

    # Create more data in new database
    new_person = await Person.create(name="Eve", age=28)
    print(f"✅ Created Eve in new database: {new_person.id}")

    # Method 6: Configuration-Driven Switching
    print("\n6️⃣  Configuration-Driven Database Switching")
    print("-" * 40)

    class DatabaseConfig:
        """Configuration-driven database management."""

        def __init__(self):
            self.configs = {
                "cache": {"name": "Cache-DB"},
                "analytics": {"name": "Analytics-DB"},
                "user_data": {"name": "UserData-DB"},
                "audit": {"name": "Audit-DB"},
            }
            self.databases = {}
            self.contexts = {}

        async def initialize(self):
            """Initialize all configured databases."""
            for purpose, config in self.configs.items():
                db_name = config.get("name", f"{purpose}_db")
                self.databases[purpose] = MockDatabase(name=db_name)
                self.contexts[purpose] = GraphContext(database=self.databases[purpose])
                print(f"🔧 Initialized {purpose} database")

        async def save_user(self, user_data: dict):
            """Save user to user_data database."""
            ctx = self.contexts["user_data"]
            set_default_context(ctx)
            user = await Person.create(**user_data)
            print(f"👤 Saved user to user_data database")
            return user

        async def cache_result(self, key: str, value: dict):
            """Cache result in cache database."""
            ctx = self.contexts["cache"]
            # In real app, you'd have a cache-specific model
            print(f"💾 Cached {key} in cache database")

        async def log_audit(self, action: str, user_id: str):
            """Log audit event."""
            ctx = self.contexts["audit"]
            print(f"📝 Logged audit: {action} by {user_id}")

    # Use configuration-driven approach
    db_config = DatabaseConfig()
    await db_config.initialize()

    # Different operations use different databases automatically
    user = await db_config.save_user({"name": "Frank", "age": 45})
    await db_config.cache_result("user_profile", {"name": "Frank"})
    await db_config.log_audit("user_created", user.id)

    print(f"\n✅ Database switching demonstration completed!")
    print(f"\nKey takeaways:")
    print(f"  • Databases can be switched per-operation")
    print(f"  • Context objects encapsulate database usage")
    print(f"  • Default context can be changed at runtime using set_default_context()")
    print(f"  • Environment variables enable dynamic configuration")
    print(f"  • Application lifecycle switching supports hot-swapping")
    print(f"  • Configuration-driven approach separates concerns")


if __name__ == "__main__":
    asyncio.run(demonstrate_database_switching())
