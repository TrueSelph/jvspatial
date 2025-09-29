"""
Exception Handling Demonstration for jvspatial

This example shows best practices for handling errors in jvspatial applications,
demonstrating proper exception catching, error recovery, and graceful degradation.
"""

import asyncio
import logging
from typing import Optional

from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Edge, Node, Walker
from jvspatial.exceptions import (
    ConfigurationError,
    ConnectionError,
    DatabaseError,
    EntityNotFoundError,
    GraphError,
    InvalidConfigurationError,
    JVSpatialError,
    NodeNotFoundError,
    QueryError,
    ValidationError,
    WalkerExecutionError,
    WalkerTimeoutError,
)

# Configure logging to see error details
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class User(Node):
    """User node with validation."""

    name: str = ""
    email: str = ""
    age: int = 0
    active: bool = True

    async def validate_custom(self) -> bool:
        """Custom validation that might fail."""
        if not self.name:
            raise ValidationError(
                "Name cannot be empty", field_errors={"name": "Required field"}
            )

        if self.age < 0:
            raise ValidationError(
                "Age cannot be negative", field_errors={"age": "Must be positive"}
            )

        if "@" not in self.email:
            raise ValidationError(
                "Invalid email format", field_errors={"email": "Must contain @"}
            )

        return True


class Connection(Edge):
    """Connection edge between users."""

    relationship_type: str = "friend"
    strength: float = 1.0


class UserAnalyzer(Walker):
    """Walker that analyzes users with error handling."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.processed_count = 0
        self.error_count = 0

    async def on_visit(self, here: Node) -> None:
        """Visit hook with comprehensive error handling."""
        try:
            if isinstance(here, User):
                await self.analyze_user(here)

            self.processed_count += 1

        except ValidationError as e:
            logger.warning(f"User validation failed for {here.id}: {e.message}")
            self.error_count += 1
            self.report(
                {
                    "error_type": "validation",
                    "node_id": here.id,
                    "details": e.field_errors,
                }
            )

        except Exception as e:
            logger.error(f"Unexpected error processing {here.id}: {e}")
            self.error_count += 1
            self.report(
                {"error_type": "unexpected", "node_id": here.id, "error": str(e)}
            )

    async def analyze_user(self, user: User) -> None:
        """Analyze a user with potential errors."""
        # Validate the user
        await user.validate_custom()

        # Simulate external service call that might fail
        if user.name == "BadUser":
            raise RuntimeError("External service error")

        # Record analysis results
        self.report(
            {
                "user_analyzed": {
                    "id": user.id,
                    "name": user.name,
                    "active": user.active,
                    "connections": len(user.edge_ids),
                }
            }
        )


async def demonstrate_entity_operations():
    """Demonstrate entity operation error handling."""
    print("\n=== Entity Operations Error Handling ===")

    try:
        # Valid user creation
        user1 = await User.create(name="Alice", email="alice@example.com", age=30)
        print(f"✓ Created user: {user1.name}")

        # This will fail validation
        try:
            user2 = User(name="", email="invalid-email", age=-5)
            await user2.validate_custom()
        except ValidationError as e:
            print(f"✗ Validation failed: {e.message}")
            if e.field_errors:
                for field, error in e.field_errors.items():
                    print(f"  - {field}: {error}")

        # Try to get non-existent entity
        try:
            missing_user = await User.get("nonexistent-id")
            if missing_user is None:
                print("✓ Gracefully handled missing entity (returned None)")
        except EntityNotFoundError as e:
            print(f"✗ Entity not found: {e.entity_type} with ID {e.entity_id}")

        # Find operation with error handling
        try:
            users = await User.find({"context.active": True})
            print(f"✓ Found {len(users)} active users")
        except QueryError as e:
            print(f"✗ Query failed: {e.message}")
            print(f"  Query: {e.query}")

    except JVSpatialError as e:
        print(f"✗ jvspatial error: {e.message}")
        if e.details:
            print(f"  Details: {e.details}")

    except Exception as e:
        print(f"✗ Unexpected error: {e}")


async def demonstrate_database_error_handling():
    """Demonstrate database error handling with fallback strategies."""
    print("\n=== Database Error Handling ===")

    try:
        # Try to create context with potentially failing database
        ctx = GraphContext()
        print("✓ Database connection established")

        # Simulate database operation that might fail
        try:
            users = await User.find({"context.name": {"$regex": "^A"}})
            print(f"✓ Complex query succeeded, found {len(users)} users")
        except QueryError as e:
            print(f"✗ Complex query failed: {e.message}")
            # Fallback to simpler query
            try:
                all_users = await User.all()
                filtered_users = [u for u in all_users if u.name.startswith("A")]
                print(f"✓ Fallback succeeded, found {len(filtered_users)} users")
            except Exception as fallback_error:
                print(f"✗ Fallback also failed: {fallback_error}")

    except ConnectionError as e:
        print(f"✗ Database connection failed: {e.message}")
        print(f"  Database type: {e.database_type}")
        print("  Consider checking connection string or database availability")

    except DatabaseError as e:
        print(f"✗ Database error: {e.message}")


async def demonstrate_walker_error_handling():
    """Demonstrate walker error handling and recovery."""
    print("\n=== Walker Error Handling ===")

    try:
        # Create test users (some valid, some problematic)
        users = [
            await User.create(name="Alice", email="alice@example.com", age=30),
            await User.create(name="Bob", email="bob@example.com", age=25),
            await User.create(
                name="BadUser", email="bad@example.com", age=35
            ),  # Will cause error
        ]

        # Create connections
        connection = await Connection.create(
            left=users[0], right=users[1], relationship_type="friend"
        )

        # Run walker with error handling
        analyzer = UserAnalyzer()

        try:
            # Set protection limits for demonstration
            analyzer.max_execution_time = 10.0  # 10 seconds max
            analyzer.max_steps = 100

            result_walker = await analyzer.spawn(users[0])

            # Get results and error summary
            report = result_walker.get_report()
            print(f"✓ Walker completed successfully")
            print(f"  Processed: {analyzer.processed_count} nodes")
            print(f"  Errors: {analyzer.error_count}")
            print(f"  Report items: {len(report)}")

            # Show error details
            errors = [
                item
                for item in report
                if isinstance(item, dict) and "error_type" in item
            ]
            for error in errors:
                print(f"  Error: {error['error_type']} on {error['node_id']}")

        except WalkerTimeoutError as e:
            print(f"✗ Walker timed out after {e.timeout_seconds} seconds")
            print(f"  Walker: {e.walker_class}")
            # Can still access partial results
            partial_report = analyzer.get_report()
            print(f"  Partial results: {len(partial_report)} items")

        except WalkerExecutionError as e:
            print(f"✗ Walker execution failed: {e.message}")
            print(f"  Walker: {e.walker_class}")

    except Exception as e:
        print(f"✗ Unexpected walker error: {e}")


async def demonstrate_configuration_error_handling():
    """Demonstrate configuration error handling."""
    print("\n=== Configuration Error Handling ===")

    try:
        from jvspatial.db.factory import get_database

        # Try to get database with invalid configuration
        try:
            db = get_database("invalid_database_type")
        except InvalidConfigurationError as e:
            print(f"✗ Invalid database configuration: {e.message}")
            print(f"  Config key: {e.config_key}")
            print(f"  Config value: {e.config_value}")

            # Fall back to default
            try:
                db = get_database("json")
                print("✓ Successfully fell back to JSON database")
            except ConfigurationError as fallback_error:
                print(f"✗ Fallback failed: {fallback_error}")

    except Exception as e:
        print(f"✗ Configuration error: {e}")


async def demonstrate_graph_error_handling():
    """Demonstrate graph structure error handling."""
    print("\n=== Graph Structure Error Handling ===")

    try:
        # Create nodes
        user1 = await User.create(name="Alice", email="alice@example.com", age=30)
        user2 = await User.create(name="Bob", email="bob@example.com", age=25)

        # Try to create connection with validation
        try:
            connection = await Connection.create(
                left=user1,
                right=user2,
                relationship_type="friend",
                strength=1.5,  # Valid strength
            )
            print("✓ Connection created successfully")

            # Validate graph structure
            connected_nodes = await user1.nodes("out")
            print(f"✓ Found {len(connected_nodes)} connected nodes")

        except ValidationError as e:
            print(f"✗ Connection validation failed: {e.message}")

        except GraphError as e:
            print(f"✗ Graph structure error: {e.message}")

    except Exception as e:
        print(f"✗ Unexpected graph error: {e}")


async def demonstrate_comprehensive_error_strategy():
    """Demonstrate a comprehensive error handling strategy."""
    print("\n=== Comprehensive Error Handling Strategy ===")

    error_summary = {
        "validation_errors": 0,
        "database_errors": 0,
        "walker_errors": 0,
        "configuration_errors": 0,
        "unexpected_errors": 0,
        "successful_operations": 0,
    }

    operations = [
        ("Entity Creation", demonstrate_entity_operations),
        ("Database Operations", demonstrate_database_error_handling),
        ("Walker Processing", demonstrate_walker_error_handling),
        ("Configuration Setup", demonstrate_configuration_error_handling),
        ("Graph Operations", demonstrate_graph_error_handling),
    ]

    for operation_name, operation_func in operations:
        try:
            print(f"\nExecuting: {operation_name}")
            await operation_func()
            error_summary["successful_operations"] += 1

        except ValidationError:
            error_summary["validation_errors"] += 1
            logger.error(f"Validation error in {operation_name}")
        except DatabaseError:
            error_summary["database_errors"] += 1
            logger.error(f"Database error in {operation_name}")
        except WalkerExecutionError:
            error_summary["walker_errors"] += 1
            logger.error(f"Walker error in {operation_name}")
        except ConfigurationError:
            error_summary["configuration_errors"] += 1
            logger.error(f"Configuration error in {operation_name}")
        except JVSpatialError as e:
            error_summary["unexpected_errors"] += 1
            logger.error(f"jvspatial error in {operation_name}: {e}")
        except Exception as e:
            error_summary["unexpected_errors"] += 1
            logger.error(f"Unexpected error in {operation_name}: {e}")

    # Print summary
    print("\n=== Error Summary ===")
    total_operations = len(operations)
    for error_type, count in error_summary.items():
        print(f"{error_type.replace('_', ' ').title()}: {count}")

    success_rate = (error_summary["successful_operations"] / total_operations) * 100
    print(f"\nOverall Success Rate: {success_rate:.1f}%")


async def main():
    """Main demonstration function."""
    print("🚀 jvspatial Exception Handling Demonstration")
    print("=" * 50)

    try:
        await demonstrate_comprehensive_error_strategy()

    except Exception as e:
        logger.critical(f"Critical error in main: {e}")
        raise

    print("\n✅ Exception handling demonstration completed!")
    print("\nKey Takeaways:")
    print("1. Always catch specific exception types before generic ones")
    print("2. Use exception details and field_errors for debugging")
    print("3. Implement fallback strategies for critical operations")
    print("4. Log errors appropriately for monitoring and debugging")
    print("5. Design graceful degradation for non-critical failures")


if __name__ == "__main__":
    asyncio.run(main())
