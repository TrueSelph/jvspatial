"""
Testing with GraphContext Example

Shows how the GraphContext dependency injection pattern makes testing much easier
by providing database isolation and dependency injection capabilities.

This demonstrates:
- Test isolation with separate databases
- Mock database injection
- Setup/teardown patterns
- Integration vs unit testing approaches
"""

import asyncio
import shutil
import tempfile
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock

from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Edge, Node, Walker, on_visit
from jvspatial.db.database import Database
from jvspatial.db.factory import get_database


# Test entities
class Product(Node):
    """Product in an e-commerce system."""

    name: str
    price: float = 0.0
    category: str = ""
    in_stock: bool = True


class Order(Node):
    """Customer order."""

    customer_id: str
    total: float = 0.0
    status: str = "pending"


class Contains(Edge):
    """Edge connecting Order to Product."""

    quantity: int = 1


class InventoryWalker(Walker):
    """Walker that processes inventory and orders."""

    @on_visit(Order)
    async def process_order(self, here: Order):
        """Process an order by checking inventory."""
        self.response.setdefault("processed_orders", [])
        self.response["processed_orders"].append(here.id)

        # Get products in this order
        edges = await here.edges()
        contains_edges = [e for e in edges if isinstance(e, Contains)]

        total_cost = 0.0
        for edge in contains_edges:
            product_id = edge.target if edge.source == here.id else edge.source
            product = await Product.get(product_id)
            if product and product.in_stock:
                total_cost += product.price * edge.quantity

        here.total = total_cost
        here.status = "processed"
        await here.save()


class TestFramework:
    """Simple testing framework demonstrating GraphContext patterns."""

    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0

    def assert_equal(self, actual, expected, message=""):
        """Simple assertion helper."""
        if actual == expected:
            self.tests_passed += 1
            print(f"✅ PASS: {message}")
        else:
            self.tests_failed += 1
            print(f"❌ FAIL: {message}")
            print(f"   Expected: {expected}")
            print(f"   Actual: {actual}")

    def summary(self):
        """Print test summary."""
        total = self.tests_passed + self.tests_failed
        print(f"\n📊 Test Summary: {self.tests_passed}/{total} passed")
        if self.tests_failed > 0:
            print(f"❌ {self.tests_failed} tests failed")
        else:
            print("🎉 All tests passed!")


async def test_with_isolated_database():
    """
    Pattern 1: Test Isolation with Separate Databases

    Each test gets its own database, preventing interference between tests.
    """
    print("=" * 60)
    print("PATTERN 1: TEST ISOLATION WITH SEPARATE DATABASES")
    print("=" * 60)

    framework = TestFramework()

    # Test 1: Create products in isolated database
    test1_db_path = tempfile.mkdtemp()
    test1_ctx = GraphContext(
        database=get_database(db_type="json", base_path=test1_db_path)
    )

    laptop = await test1_ctx.create_node(
        Product, name="Laptop", price=999.99, category="Electronics"
    )
    mouse = await test1_ctx.create_node(
        Product, name="Mouse", price=29.99, category="Electronics"
    )

    framework.assert_equal(laptop.name, "Laptop", "Product creation in test1")

    # Test 2: Different products in different isolated database
    test2_db_path = tempfile.mkdtemp()
    test2_ctx = GraphContext(
        database=get_database(db_type="json", base_path=test2_db_path)
    )

    book = await test2_ctx.create_node(
        Product, name="Book", price=19.99, category="Books"
    )

    framework.assert_equal(book.name, "Book", "Product creation in test2")

    # Verify isolation: test1 database shouldn't have test2 products
    test1_products = await test1_ctx.database.find("node", {})
    test2_products = await test2_ctx.database.find("node", {})

    framework.assert_equal(len(test1_products), 2, "Test1 database has 2 products")
    framework.assert_equal(len(test2_products), 1, "Test2 database has 1 product")

    # Cleanup
    shutil.rmtree(test1_db_path, ignore_errors=True)
    shutil.rmtree(test2_db_path, ignore_errors=True)

    framework.summary()
    return framework.tests_failed == 0


async def test_with_mock_database():
    """
    Pattern 2: Mock Database Injection

    Inject a mock database for unit testing without actual persistence.
    """
    print("\n" + "=" * 60)
    print("PATTERN 2: MOCK DATABASE INJECTION")
    print("=" * 60)

    framework = TestFramework()

    # Create mock database
    mock_db = AsyncMock(spec=Database)
    mock_db.save.return_value = None
    mock_db.get.return_value = {
        "id": "n:Product:mock123",
        "name": "Product",
        "context": {"name": "Mock Product", "price": 99.99, "category": "Test"},
    }

    # Use mock database with GraphContext
    mock_ctx = GraphContext(database=mock_db)

    # Test product creation - should use mock
    product = await mock_ctx.create_node(
        Product, name="Mock Product", price=99.99, category="Test"
    )

    # Verify mock was called
    framework.assert_equal(mock_db.save.called, True, "Mock database save was called")
    framework.assert_equal(
        product.name, "Mock Product", "Mock product created correctly"
    )

    # Test retrieval
    retrieved = await mock_ctx.get_node("n:Product:mock123", Product)
    framework.assert_equal(
        retrieved.name, "Mock Product", "Mock product retrieved correctly"
    )
    framework.assert_equal(mock_db.get.called, True, "Mock database get was called")

    framework.summary()
    return framework.tests_failed == 0


async def test_integration_with_real_database():
    """
    Pattern 3: Integration Testing with Real Database

    Use a real database for integration tests while maintaining isolation.
    """
    print("\n" + "=" * 60)
    print("PATTERN 3: INTEGRATION TESTING WITH REAL DATABASE")
    print("=" * 60)

    framework = TestFramework()

    # Create isolated integration test database
    integration_db_path = tempfile.mkdtemp()
    integration_db = get_database(db_type="json", base_path=integration_db_path)
    integration_ctx = GraphContext(database=integration_db)

    print(f"🏗️  Integration test database: {integration_db_path}")

    # Test complete order processing workflow
    laptop = await integration_ctx.create_node(
        Product,
        name="Gaming Laptop",
        price=1299.99,
        category="Electronics",
        in_stock=True,
    )

    order = await integration_ctx.create_node(
        Order, customer_id="customer_123", status="pending"
    )

    # Connect order to product
    contains = await integration_ctx.create_edge(
        Contains, left=order, right=laptop, quantity=2
    )

    # Process order with walker
    walker = InventoryWalker()
    await walker.spawn(start=order)

    # Verify results
    processed_orders = walker.response.get("processed_orders", [])
    framework.assert_equal(len(processed_orders), 1, "One order processed")
    framework.assert_equal(processed_orders[0], order.id, "Correct order processed")

    # Check order was updated
    updated_order = await integration_ctx.get_node(order.id, Order)
    framework.assert_equal(updated_order.status, "processed", "Order status updated")
    framework.assert_equal(
        updated_order.total, 2599.98, "Order total calculated correctly"
    )

    # Cleanup
    shutil.rmtree(integration_db_path, ignore_errors=True)

    framework.summary()
    return framework.tests_failed == 0


async def test_setup_teardown_pattern():
    """
    Pattern 4: Setup/Teardown with GraphContext

    Shows how to implement proper test setup and teardown with GraphContext.
    """
    print("\n" + "=" * 60)
    print("PATTERN 4: SETUP/TEARDOWN PATTERN")
    print("=" * 60)

    framework = TestFramework()
    test_contexts = []

    try:
        # Setup: Create test contexts for different test scenarios
        for i in range(3):
            db_path = tempfile.mkdtemp()
            ctx = GraphContext(database=get_database(db_type="json", base_path=db_path))
            test_contexts.append((ctx, db_path))

            # Setup test data
            await ctx.create_node(
                Product, name=f"Test Product {i}", price=float(i * 100)
            )

        print(f"🔧 Setup: Created {len(test_contexts)} test contexts")

        # Run tests
        for i, (ctx, _) in enumerate(test_contexts):
            products = await ctx.database.find("node", {})
            framework.assert_equal(len(products), 1, f"Test context {i} has 1 product")

        framework.summary()

    finally:
        # Teardown: Clean up all test databases
        for ctx, db_path in test_contexts:
            shutil.rmtree(db_path, ignore_errors=True)

        print(f"🧹 Teardown: Cleaned up {len(test_contexts)} test databases")

    return framework.tests_failed == 0


async def test_original_api_compatibility():
    """
    Pattern 5: Verify Original API Still Works

    Ensure that existing test code continues to work without modification.
    """
    print("\n" + "=" * 60)
    print("PATTERN 5: ORIGINAL API COMPATIBILITY")
    print("=" * 60)

    framework = TestFramework()

    # All the classic testing patterns still work:

    # 1. Create entities the old way
    product = await Product.create(name="Legacy Product", price=49.99)
    order = await Order.create(customer_id="legacy_customer")

    framework.assert_equal(product.name, "Legacy Product", "Legacy product creation")
    framework.assert_equal(
        order.customer_id, "legacy_customer", "Legacy order creation"
    )

    # 2. Connect them the old way
    edge = await order.connect(product, Contains, quantity=3)

    framework.assert_equal(isinstance(edge, Contains), True, "Legacy connection")
    framework.assert_equal(edge.quantity, 3, "Legacy edge properties")

    # 3. Retrieve the old way
    retrieved_product = await Product.get(product.id)
    retrieved_order = await Order.get(order.id)

    framework.assert_equal(retrieved_product.name, "Legacy Product", "Legacy retrieval")
    framework.assert_equal(
        retrieved_order.customer_id, "legacy_customer", "Legacy order retrieval"
    )

    # 4. Walker processing the old way
    walker = InventoryWalker()
    await walker.spawn(start=order)

    processed = walker.response.get("processed_orders", [])
    framework.assert_equal(len(processed), 1, "Legacy walker processing")

    framework.summary()
    return framework.tests_failed == 0


async def main():
    """
    Run all testing pattern demonstrations.
    """
    print("🧪 Testing with GraphContext Demo")
    print("Shows how GraphContext makes testing much easier and more reliable")

    results = []

    # Run all test pattern demonstrations
    results.append(await test_with_isolated_database())
    results.append(await test_with_mock_database())
    results.append(await test_integration_with_real_database())
    results.append(await test_setup_teardown_pattern())
    results.append(await test_original_api_compatibility())

    print("\n" + "=" * 60)
    print("🎯 TESTING DEMO SUMMARY")
    print("=" * 60)

    passed_tests = sum(results)
    total_tests = len(results)

    print(f"Test Patterns: {passed_tests}/{total_tests} passed")

    if passed_tests == total_tests:
        print("🎉 All testing patterns work correctly!")
        print("\nKey Benefits Demonstrated:")
        print("✅ Database isolation prevents test interference")
        print("✅ Mock injection enables pure unit testing")
        print("✅ Real database integration testing")
        print("✅ Proper setup/teardown patterns")
        print("✅ 100% backwards compatibility with existing tests")
    else:
        print("❌ Some testing patterns need attention")

    return passed_tests == total_tests


if __name__ == "__main__":
    asyncio.run(main())
