"""Example demonstrating multi-database support with prime database.

This example shows how to:
1. Use the prime database for core persistence (auth, sessions)
2. Create and register additional databases
3. Switch between databases
4. Remove/unregister non-prime databases
5. Ensure authentication always uses prime database
"""

import asyncio
import tempfile
from pathlib import Path

from jvspatial import Object, Server
from jvspatial.core.context import GraphContext
from jvspatial.db import (
    DatabaseManager,
    create_database,
    get_current_database,
    get_database_manager,
    get_prime_database,
    switch_database,
    unregister_database,
)


# Define entities
class User(Object):
    """User entity - stored in prime database for authentication."""

    email: str = ""
    name: str = ""


class Product(Object):
    """Product entity - can be stored in application database."""

    name: str = ""
    price: float = 0.0
    category: str = ""


async def demonstrate_multi_database():
    """Demonstrate multi-database usage with prime database."""
    print("=" * 60)
    print("Multi-Database Example")
    print("=" * 60)

    # Create temporary directories for databases
    prime_dir = tempfile.mkdtemp(prefix="prime_db_")
    app_dir = tempfile.mkdtemp(prefix="app_db_")

    try:
        # 1. Initialize DatabaseManager (creates prime database automatically)
        print("\n1. Initializing DatabaseManager...")
        manager = get_database_manager()
        prime_db = manager.get_prime_database()
        print(f"   ✅ Prime database created: {type(prime_db).__name__}")

        # 2. Create and register additional database
        print("\n2. Creating and registering application database...")
        app_db = create_database("json", base_path=app_dir, register=True, name="app")
        print(f"   ✅ Application database registered: 'app'")

        # 3. List all databases
        print("\n3. Listing all databases...")
        databases = manager.list_databases()
        for name, info in databases.items():
            print(
                f"   - {name}: {info['type']} (prime={info['is_prime']}, current={info['is_current']})"
            )

        # 4. Use prime database for authentication data
        print("\n4. Using prime database for authentication (User entities)...")
        prime_ctx = GraphContext(database=prime_db)

        # Create user in prime database
        user = User(email="admin@example.com", name="Admin User")
        await prime_ctx.save(user)
        print(f"   ✅ Created user in prime database: {user.id}")

        # Verify user is in prime database using context
        retrieved_user = await prime_ctx.get(User, user.id)
        assert retrieved_user is not None, "User should be found in prime database"
        print(f"   ✅ Retrieved user from prime database: {retrieved_user.email}")

        # 5. Switch to application database for product data
        print("\n5. Switching to application database for products...")
        manager.set_current_database("app")
        app_ctx = GraphContext(database=manager.get_current_database())

        # Create product in app database
        product = Product(name="Widget", price=19.99, category="Tools")
        await app_ctx.save(product)
        print(f"   ✅ Created product in app database: {product.id}")

        # Verify product is in app database using context
        retrieved_product = await app_ctx.get(Product, product.id)
        assert retrieved_product is not None, "Product should be found in app database"
        print(f"   ✅ Retrieved product from app database: {retrieved_product.name}")

        # 6. Verify isolation - user should NOT be in app database
        print("\n6. Verifying database isolation...")
        # Verify by trying to retrieve the saved entities from each database
        # Try to get user from app database (should fail)
        user_from_app = await app_ctx.get(User, user.id)
        assert user_from_app is None, "User should not be found in app database"

        # Try to get product from prime database (should fail)
        product_from_prime = await prime_ctx.get(Product, product.id)
        assert (
            product_from_prime is None
        ), "Product should not be found in prime database"

        # Verify user is in prime database
        user_from_prime = await prime_ctx.get(User, user.id)
        assert user_from_prime is not None, "User should be found in prime database"
        assert user_from_prime.email == user.email, "User data should match"

        # Verify product is in app database
        product_from_app = await app_ctx.get(Product, product.id)
        assert product_from_app is not None, "Product should be found in app database"
        assert product_from_app.name == product.name, "Product data should match"

        print(f"   ✅ User found in prime database: {user_from_prime.email}")
        print(f"   ✅ Product found in app database: {product_from_app.name}")
        print(f"   ✅ User NOT found in app database (isolation verified)")
        print(f"   ✅ Product NOT found in prime database (isolation verified)")

        # 8. Switch back to prime database
        print("\n7. Switching back to prime database...")
        manager.set_current_database("prime")
        current_db = manager.get_current_database()
        assert current_db == prime_db, "Current database should be prime"
        print("   ✅ Switched back to prime database")

        # 9. Use convenience functions
        print("\n8. Using convenience functions...")
        prime_db_via_func = get_prime_database()
        current_db_via_func = get_current_database()
        assert prime_db_via_func == prime_db, "get_prime_database() should return prime"
        assert (
            current_db_via_func == prime_db
        ), "get_current_database() should return prime"
        print("   ✅ Convenience functions work correctly")

        # Switch using convenience function
        switch_database("app")
        current_after_switch = get_current_database()
        assert current_after_switch == app_db, "switch_database() should work"
        print("   ✅ switch_database() convenience function works")

        # 9. Remove/unregister a non-prime database
        print("\n9. Removing a non-prime database...")
        print("   Current databases before removal:")
        databases_before = manager.list_databases()
        for name, info in databases_before.items():
            print(
                f"     - {name}: {info['type']} (prime={info['is_prime']}, current={info['is_current']})"
            )

        # Switch to app database to demonstrate it switches back to prime when removed
        manager.set_current_database("app")
        print(
            f"   ✅ Switched to 'app' database (current: {manager._current_database_name})"
        )

        # Remove the app database using unregister_database()
        print("\n   Removing 'app' database using unregister_database('app')...")
        unregister_database("app")

        # Verify it was removed
        databases_after = manager.list_databases()
        assert "app" not in databases_after, "App database should be unregistered"
        assert (
            manager.get_current_database() == prime_db
        ), "Should switch to prime when current is removed"
        print("   ✅ Application database removed successfully")
        print(
            f"   ✅ Current database automatically switched to: {manager._current_database_name}"
        )

        print("\n   Remaining databases after removal:")
        for name, info in databases_after.items():
            print(
                f"     - {name}: {info['type']} (prime={info['is_prime']}, current={info['is_current']})"
            )

        # 10. Demonstrate removing multiple non-prime databases
        print("\n10. Demonstrating removal of multiple non-prime databases...")

        # Create and register multiple databases
        analytics_dir = tempfile.mkdtemp(prefix="analytics_db_")
        logging_dir = tempfile.mkdtemp(prefix="logging_db_")

        analytics_db = create_database(
            "json", base_path=analytics_dir, register=True, name="analytics"
        )
        logging_db = create_database(
            "json", base_path=logging_dir, register=True, name="logging"
        )
        print(f"   ✅ Created and registered: analytics, logging")

        databases_all = manager.list_databases()
        print(f"   Total databases: {len(databases_all)}")
        for name in databases_all.keys():
            print(f"     - {name}")

        # Remove analytics database
        print("\n   Removing 'analytics' database...")
        unregister_database("analytics")
        databases_after_analytics = manager.list_databases()
        assert (
            "analytics" not in databases_after_analytics
        ), "Analytics database should be removed"
        assert (
            "logging" in databases_after_analytics
        ), "Logging database should still exist"
        print("   ✅ Analytics database removed")
        print(f"   Remaining: {list(databases_after_analytics.keys())}")

        # Remove logging database
        print("\n   Removing 'logging' database...")
        unregister_database("logging")
        databases_final = manager.list_databases()
        assert "logging" not in databases_final, "Logging database should be removed"
        assert len(databases_final) == 1, "Only prime database should remain"
        assert "prime" in databases_final, "Prime database must always remain"
        print("   ✅ Logging database removed")
        print(f"   ✅ Only prime database remains: {list(databases_final.keys())}")

        # 11. Demonstrate error handling - cannot remove prime database
        print("\n11. Demonstrating protection of prime database...")
        print("   Attempting to remove prime database (should fail)...")
        try:
            unregister_database("prime")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            print(f"   ✅ Correctly prevented removing prime database: {e}")
            print("   ✅ Prime database is protected and cannot be removed")

        print("\n" + "=" * 60)
        print("✅ Multi-database example completed successfully!")
        print("=" * 60)

    finally:
        # Cleanup
        import os
        import shutil

        # Clean up all temporary directories
        temp_dirs = [prime_dir, app_dir]

        # Also clean up analytics/logging directories if they were created
        try:
            for item in os.listdir("."):
                if item.startswith("analytics_db_") or item.startswith("logging_db_"):
                    full_path = os.path.join(".", item)
                    if os.path.isdir(full_path):
                        temp_dirs.append(full_path)
        except Exception:
            pass  # Ignore errors when listing directory

        # Remove all temporary directories
        for dir_path in temp_dirs:
            if dir_path and os.path.exists(dir_path):
                shutil.rmtree(dir_path, ignore_errors=True)


async def demonstrate_server_with_multi_database():
    """Demonstrate Server using prime database for authentication."""
    print("\n" + "=" * 60)
    print("Server with Multi-Database Example")
    print("=" * 60)

    prime_dir = tempfile.mkdtemp(prefix="server_prime_")
    app_dir = tempfile.mkdtemp(prefix="server_app_")

    try:
        # Create server - this initializes prime database
        print("\n1. Creating server (initializes prime database)...")
        server = Server(
            title="Multi-DB API",
            db_type="json",
            db_path=prime_dir,
            auth_enabled=True,
        )

        # Verify prime database is set up
        manager = get_database_manager()
        prime_db = manager.get_prime_database()
        print(f"   ✅ Prime database initialized: {type(prime_db).__name__}")

        # Create and register application database
        print("\n2. Registering application database...")
        app_db = create_database(
            "json", base_path=app_dir, register=True, name="app_data"
        )
        manager.set_current_database("app_data")
        print("   ✅ Application database registered and set as current")

        # Verify authentication uses prime database
        print("\n3. Verifying authentication uses prime database...")
        from jvspatial.api.auth.service import AuthenticationService

        auth_service = AuthenticationService()
        # AuthenticationService should use prime database
        auth_ctx_db = auth_service.context.database
        assert auth_ctx_db == prime_db, "Authentication should use prime database"
        print("   ✅ Authentication service uses prime database")

        print("\n" + "=" * 60)
        print("✅ Server multi-database example completed!")
        print("=" * 60)

    finally:
        import shutil

        shutil.rmtree(prime_dir, ignore_errors=True)
        shutil.rmtree(app_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(demonstrate_multi_database())
    asyncio.run(demonstrate_server_with_multi_database())
