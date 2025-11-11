"""Example demonstrating SQLite database integration.

This example shows how to:
1. Create and configure SQLite databases
2. Use SQLite with GraphContext and entities
3. Perform CRUD operations with SQLite
4. Use SQLite as prime database
5. Configure SQLite via environment variables
6. Use SQLite with Server
"""

import asyncio
import os
import tempfile
from pathlib import Path

from jvspatial import Node, Object, Server
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.db import (
    create_database,
    get_database_manager,
    get_prime_database,
    switch_database,
)


# Define entities
class User(Node):
    """User entity for authentication."""

    email: str = ""
    name: str = ""
    active: bool = True


class Product(Object):
    """Product entity for application data."""

    name: str = ""
    price: float = 0.0
    category: str = ""
    in_stock: bool = True


class Order(Object):
    """Order entity."""

    user_id: str = ""
    product_id: str = ""
    quantity: int = 0
    total: float = 0.0


async def demonstrate_sqlite_basic():
    """Demonstrate basic SQLite usage."""
    print("=" * 60)
    print("SQLite Database Example - Basic Usage")
    print("=" * 60)

    # Create temporary database file
    temp_dir = tempfile.mkdtemp(prefix="sqlite_example_")
    db_path = Path(temp_dir) / "example.db"

    try:
        # 1. Create SQLite database
        print("\n1. Creating SQLite database...")
        db = create_database("sqlite", db_path=str(db_path))
        print(f"   ✅ SQLite database created at: {db_path}")
        print(f"   ✅ Database type: {type(db).__name__}")

        # 2. Create GraphContext with SQLite
        print("\n2. Creating GraphContext with SQLite...")
        ctx = GraphContext(database=db)
        set_default_context(ctx)
        print("   ✅ GraphContext initialized with SQLite")

        # 3. Create entities
        print("\n3. Creating entities...")
        user = await User.create(
            email="alice@example.com", name="Alice Johnson", active=True
        )
        print(f"   ✅ Created user: {user.name} (ID: {user.id})")

        product1 = await Product.create(
            name="Laptop", price=999.99, category="Electronics", in_stock=True
        )
        product2 = await Product.create(
            name="Mouse", price=29.99, category="Electronics", in_stock=True
        )
        print(f"   ✅ Created products: {product1.name}, {product2.name}")

        # 4. Retrieve entities
        print("\n4. Retrieving entities...")
        retrieved_user = await User.get(user.id)
        if retrieved_user:
            print(
                f"   ✅ Retrieved user: {retrieved_user.name} ({retrieved_user.email})"
            )

        products = await Product.find({"context.category": "Electronics"})
        print(f"   ✅ Found {len(products)} electronics products")

        # 5. Update entity
        print("\n5. Updating entity...")
        if retrieved_user:
            retrieved_user.active = False
            await retrieved_user.save()
            print(f"   ✅ Updated user active status: {retrieved_user.active}")

        # 6. Query entities
        print("\n6. Querying entities...")
        active_users = await User.find({"context.active": True})
        print(f"   ✅ Found {len(active_users)} active users")

        expensive_products = await Product.find({"context.price": {"$gte": 100}})
        print(f"   ✅ Found {len(expensive_products)} products >= $100")

        # 7. Delete entity
        print("\n7. Deleting entity...")
        await product2.delete()
        remaining_products = await Product.find({})
        print(f"   ✅ Deleted product. Remaining products: {len(remaining_products)}")

        # 8. Close database connection
        print("\n8. Closing database connection...")
        await db.close()
        print("   ✅ Database connection closed")

    finally:
        # Cleanup
        try:
            if db_path.exists():
                db_path.unlink()
            Path(temp_dir).rmdir()
        except Exception:
            pass


async def demonstrate_sqlite_with_manager():
    """Demonstrate SQLite with DatabaseManager."""
    print("\n" + "=" * 60)
    print("SQLite Database Example - Multi-Database Management")
    print("=" * 60)

    temp_dir = tempfile.mkdtemp(prefix="sqlite_manager_")
    prime_db_path = Path(temp_dir) / "prime.db"
    app_db_path = Path(temp_dir) / "app.db"

    try:
        # 1. Create SQLite as prime database
        print("\n1. Creating SQLite prime database...")
        prime_db = create_database("sqlite", db_path=str(prime_db_path))
        manager = get_database_manager()
        # Note: In a real app, you'd set this via environment variable
        # JVSPATIAL_DB_TYPE=sqlite JVSPATIAL_SQLITE_PATH=./prime.db
        print(f"   ✅ Prime database created: {prime_db_path}")

        # 2. Create application SQLite database
        print("\n2. Creating application SQLite database...")
        app_db = create_database(
            "sqlite", db_path=str(app_db_path), register=True, name="app"
        )
        print(f"   ✅ Application database created: {app_db_path}")

        # 3. Use prime database for authentication
        print("\n3. Using prime database for authentication...")
        prime_ctx = GraphContext(database=prime_db)
        set_default_context(prime_ctx)

        admin_user = await User.create(
            email="admin@example.com", name="Admin User", active=True
        )
        print(f"   ✅ Created admin user in prime database: {admin_user.email}")

        # 4. Switch to application database
        print("\n4. Switching to application database...")
        switch_database("app")
        app_ctx = GraphContext(database=app_db)
        set_default_context(app_ctx)

        # Create products in application database
        product = await Product.create(
            name="Widget", price=49.99, category="Tools", in_stock=True
        )
        print(f"   ✅ Created product in app database: {product.name}")

        # 5. Verify isolation
        print("\n5. Verifying database isolation...")
        # User should not be in app database
        user_in_app = await app_ctx.get(User, admin_user.id)
        assert user_in_app is None, "User should not be in app database"
        print("   ✅ User correctly isolated in prime database")

        # Product should not be in prime database
        product_in_prime = await prime_ctx.get(Product, product.id)
        assert product_in_prime is None, "Product should not be in prime database"
        print("   ✅ Product correctly isolated in app database")

        # 6. List databases
        print("\n6. Listing all databases...")
        databases = manager.list_databases()
        for name, info in databases.items():
            print(
                f"   - {name}: {info['type']} (prime={info['is_prime']}, "
                f"current={info['is_current']})"
            )

        # Cleanup
        await prime_db.close()
        await app_db.close()

    finally:
        # Cleanup
        try:
            if prime_db_path.exists():
                prime_db_path.unlink()
            if app_db_path.exists():
                app_db_path.unlink()
            Path(temp_dir).rmdir()
        except Exception:
            pass


async def demonstrate_sqlite_configuration():
    """Demonstrate SQLite configuration options."""
    print("\n" + "=" * 60)
    print("SQLite Database Example - Configuration Options")
    print("=" * 60)

    temp_dir = tempfile.mkdtemp(prefix="sqlite_config_")
    db_path = Path(temp_dir) / "configured.db"

    try:
        # 1. Default configuration
        print("\n1. Creating SQLite with default configuration...")
        db_default = create_database("sqlite", db_path=str(db_path))
        print(f"   ✅ Default timeout: {db_default.timeout}s")
        print(f"   ✅ Default journal_mode: {db_default.journal_mode}")
        print(f"   ✅ Default synchronous: {db_default.synchronous}")
        await db_default.close()

        # 2. Custom configuration
        print("\n2. Creating SQLite with custom configuration...")
        db_custom = create_database(
            "sqlite",
            db_path=str(db_path),
            timeout=10.0,
            journal_mode="DELETE",
            synchronous="FULL",
        )
        print(f"   ✅ Custom timeout: {db_custom.timeout}s")
        print(f"   ✅ Custom journal_mode: {db_custom.journal_mode}")
        print(f"   ✅ Custom synchronous: {db_custom.synchronous}")

        # 3. Environment variable configuration
        print("\n3. SQLite can be configured via environment variables:")
        print("   - JVSPATIAL_DB_TYPE=sqlite")
        print("   - JVSPATIAL_SQLITE_PATH=./jvdb/sqlite/jvspatial.db")
        print("   Example:")
        print('   export JVSPATIAL_DB_TYPE="sqlite"')
        print('   export JVSPATIAL_SQLITE_PATH="./myapp.db"')

        await db_custom.close()

    finally:
        # Cleanup
        try:
            if db_path.exists():
                db_path.unlink()
            Path(temp_dir).rmdir()
        except Exception:
            pass


async def demonstrate_sqlite_with_server():
    """Demonstrate SQLite with Server."""
    print("\n" + "=" * 60)
    print("SQLite Database Example - Server Integration")
    print("=" * 60)

    temp_dir = tempfile.mkdtemp(prefix="sqlite_server_")
    db_path = Path(temp_dir) / "server.db"

    try:
        # Create server with SQLite
        print("\n1. Creating Server with SQLite database...")
        server = Server(
            title="SQLite API Example",
            description="Example API using SQLite database",
            version="1.0.0",
            db_type="sqlite",
            db_path=str(db_path),  # Use db_path for SQLite
            auth_enabled=False,  # Disable auth for simplicity
        )
        print(f"   ✅ Server configured with SQLite: {db_path}")

        # Set default context for entity operations
        ctx = GraphContext(database=server._graph_context.database)
        set_default_context(ctx)

        # Create some entities
        print("\n2. Creating entities via Server context...")
        user = await User.create(
            email="user@example.com", name="Test User", active=True
        )
        product = await Product.create(
            name="Test Product", price=99.99, category="Test", in_stock=True
        )
        print(f"   ✅ Created user: {user.name}")
        print(f"   ✅ Created product: {product.name}")

        # Verify entities are persisted
        print("\n3. Verifying persistence...")
        retrieved_user = await User.get(user.id)
        retrieved_product = await Product.get(product.id)
        assert retrieved_user is not None, "User should be persisted"
        assert retrieved_product is not None, "Product should be persisted"
        print("   ✅ Entities successfully persisted in SQLite")

        print("\n4. Server is ready to run:")
        print("   server.run()  # Starts uvicorn server on http://localhost:8000")

        # Note: We don't actually start the server in this example
        # to avoid blocking. In a real scenario, you would call:
        # server.run()

    finally:
        # Cleanup
        try:
            if db_path.exists():
                db_path.unlink()
            Path(temp_dir).rmdir()
        except Exception:
            pass


async def main():
    """Run all SQLite demonstrations."""
    print("\n" + "=" * 60)
    print("SQLite Database Integration Examples")
    print("=" * 60)
    print("\nThis example demonstrates:")
    print("  - Basic SQLite CRUD operations")
    print("  - SQLite with multi-database management")
    print("  - SQLite configuration options")
    print("  - SQLite with Server integration")
    print("\n" + "=" * 60)

    # Run demonstrations
    await demonstrate_sqlite_basic()
    await demonstrate_sqlite_with_manager()
    await demonstrate_sqlite_configuration()
    await demonstrate_sqlite_with_server()

    print("\n" + "=" * 60)
    print("✅ All SQLite examples completed successfully!")
    print("=" * 60)
    print("\nKey Takeaways:")
    print("  • SQLite is a lightweight, file-based database perfect for")
    print("    development and small-to-medium applications")
    print("  • SQLite databases are created with create_database('sqlite', ...)")
    print("  • SQLite works seamlessly with GraphContext and entity operations")
    print("  • SQLite can be used as prime database or application database")
    print("  • SQLite supports configuration via parameters or environment variables")
    print("  • Always close SQLite connections when done: await db.close()")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
