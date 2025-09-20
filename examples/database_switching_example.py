#!/usr/bin/env python3
"""
Database Switching Example

Demonstrates various ways to dynamically switch databases in jvspatial:
1. Per-operation database switching
2. Context-based switching
3. Default database switching
4. Environment-based switching
5. Application lifecycle switching
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict

# Add the current project to the Python path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

from jvspatial.core import Edge, GraphContext, Node
from jvspatial.db import (
    Database,
    get_database,
    get_default_database_type,
    register_database,
    set_default_database,
)


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


def mock_configurator(kwargs) -> MockDatabase:
    name = kwargs.get("name", "mock_db")
    return MockDatabase(name)


class Person(Node):
    name: str = ""
    age: int = 0


async def demonstrate_database_switching():
    """Show different ways to switch databases dynamically."""

    print("🔀 Database Switching Demonstration")
    print("=" * 50)

    # Register mock databases
    register_database("mock", MockDatabase, mock_configurator)

    # Method 1: Per-Operation Database Switching
    print("\n1️⃣  Per-Operation Database Switching")
    print("-" * 40)

    # Create different database instances
    dev_db = get_database("mock", name="Development")
    test_db = get_database("mock", name="Testing")
    prod_db = get_database("mock", name="Production")

    # Use different databases for different operations
    dev_ctx = GraphContext(database=dev_db)
    test_ctx = GraphContext(database=test_db)
    prod_ctx = GraphContext(database=prod_db)

    # Create the same person in different databases
    alice_dev = await dev_ctx.create(Person, name="Alice", age=30)
    alice_test = await test_ctx.create(Person, name="Alice", age=30)
    alice_prod = await prod_ctx.create(Person, name="Alice", age=30)

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

        # Same logic, different database
        person = await ctx.get(Person, user_id)
        if person:
            print(f"📊 Processing {person.name} in {environment} environment")
        return person

    # Process same user in different environments
    await process_user_data(alice_dev.id, "dev")
    await process_user_data(alice_test.id, "test")
    await process_user_data(alice_prod.id, "prod")

    # Method 3: Default Database Switching
    print("\n3️⃣  Default Database Switching")
    print("-" * 40)

    print(f"Current default: {get_default_database_type()}")

    # Switch default at runtime
    set_default_database("mock")
    print(f"New default: {get_default_database_type()}")

    # New contexts will use the new default
    default_ctx = GraphContext()  # Uses current default database
    bob = await default_ctx.create(Person, name="Bob", age=25)
    print("✅ Created Bob using new default database")

    # Switch back to JSON as default
    set_default_database("json")

    # Method 4: Environment-Based Switching
    print("\n4️⃣  Environment-Based Database Switching")
    print("-" * 40)

    def get_database_for_environment():
        """Get database based on environment variables."""
        env = os.getenv("APP_ENV", "development")

        if env == "production":
            return get_database("mock", name="Production-ENV")
        elif env == "testing":
            return get_database("mock", name="Testing-ENV")
        else:
            return get_database("mock", name="Development-ENV")

    # Test different environments
    environments = ["development", "testing", "production"]

    for env in environments:
        os.environ["APP_ENV"] = env
        db = get_database_for_environment()
        ctx = GraphContext(database=db)

        charlie = await ctx.create(Person, name=f"Charlie-{env}", age=35)
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

        async def initialize(self, db_type: str, **config):
            """Initialize with a specific database."""
            self.current_db = get_database(db_type, **config)
            self.context = GraphContext(database=self.current_db)
            print(f"🚀 Application initialized with {db_type}")

        async def switch_database(self, db_type: str, **config):
            """Switch to a different database."""
            print(
                f"🔄 Switching from {self.current_db.name if hasattr(self.current_db, 'name') else 'current'} to {db_type}"
            )

            # Create new database and context
            new_db = get_database(db_type, **config)
            new_context = GraphContext(database=new_db)

            # Optional: Migrate data (simplified example)
            await self._migrate_data(self.context, new_context)

            # Switch
            self.current_db = new_db
            self.context = new_context
            print("✅ Database switch completed")

        async def _migrate_data(self, old_ctx: GraphContext, new_ctx: GraphContext):
            """Simplified data migration between databases."""
            # In a real application, you'd implement proper migration logic
            print("📦 Migrating data between databases...")
            # This is just for demonstration - real migration would be more complex

    # Demonstrate application lifecycle switching
    app = ApplicationManager()

    await app.initialize("mock", name="Initial-DB")

    # Create some data
    initial_person = await app.context.create(Person, name="Diana", age=40)
    print(f"✅ Created Diana: {initial_person.id}")

    # Switch databases during runtime
    await app.switch_database("mock", name="New-DB")

    # Create more data in new database
    new_person = await app.context.create(Person, name="Eve", age=28)
    print(f"✅ Created Eve in new database: {new_person.id}")

    # Method 6: Configuration-Driven Switching
    print("\n6️⃣  Configuration-Driven Database Switching")
    print("-" * 40)

    class DatabaseConfig:
        """Configuration-driven database management."""

        def __init__(self):
            self.configs = {
                "cache": {"type": "mock", "name": "Cache-DB"},
                "analytics": {"type": "mock", "name": "Analytics-DB"},
                "user_data": {"type": "mock", "name": "UserData-DB"},
                "audit": {"type": "mock", "name": "Audit-DB"},
            }
            self.databases = {}
            self.contexts = {}

        async def initialize(self):
            """Initialize all configured databases."""
            for purpose, config in self.configs.items():
                db_type = config.pop("type")
                self.databases[purpose] = get_database(db_type, **config)
                self.contexts[purpose] = GraphContext(database=self.databases[purpose])
                print(f"🔧 Initialized {purpose} database")

        async def save_user(self, user_data: dict):
            """Save user to user_data database."""
            ctx = self.contexts["user_data"]
            user = await ctx.create(Person, **user_data)
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
    print(f"  • Default database can be changed at runtime")
    print(f"  • Environment variables enable dynamic configuration")
    print(f"  • Application lifecycle switching supports hot-swapping")
    print(f"  • Configuration-driven approach separates concerns")


if __name__ == "__main__":
    asyncio.run(demonstrate_database_switching())
