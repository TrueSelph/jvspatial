# Examples

This document showcases practical examples demonstrating jvspatial's entity-centric design and core features.

## Quick Start Examples

### Entity-Centric CRUD Operations

**Simple entity creation and MongoDB-style queries**

```python
import asyncio
from jvspatial.core import Node

class User(Node):
    name: str = ""
    email: str = ""
    department: str = ""
    active: bool = True

async def main():
    # Entity creation
    user = await User.create(name="Alice", email="alice@company.com", department="engineering")

    # MongoDB-style queries
    active_users = await User.find({"context.active": True})
    engineers = await User.find({"context.department": "engineering"})
    senior_engineers = await User.find({
        "$and": [
            {"context.department": "engineering"},
            {"context.active": True}
        ]
    })

    print(f"Found {len(active_users)} active users")
    print(f"Found {len(engineers)} engineers")
    print(f"Found {len(senior_engineers)} active engineers")

if __name__ == "__main__":
    asyncio.run(main())
```

### Walker Traversal Example

**Graph traversal with semantic filtering**

```python
import asyncio
from jvspatial.core import Node, Walker, on_visit

class User(Node):
    name: str = ""
    department: str = ""
    active: bool = True

class NetworkAnalyzer(Walker):
    def __init__(self):
        super().__init__()
        self.processed_users = []

    @on_visit(User)
    async def analyze_user(self, here: User):
        """Analyze user and traverse to colleagues."""
        self.processed_users.append(here.name)

        # Use recommended nodes() method with semantic filtering
        colleagues = await here.nodes(
            node=['User'],
            department=here.department,  # Same department
            active=True  # Only active users
        )

        # Continue traversal
        await self.visit(colleagues)

        self.response[here.id] = {
            "name": here.name,
            "department": here.department,
            "colleagues_found": len(colleagues)
        }

async def main():
    # Create test users
    alice = await User.create(name="Alice", department="engineering", active=True)
    bob = await User.create(name="Bob", department="engineering", active=True)
    charlie = await User.create(name="Charlie", department="marketing", active=True)

    # Create connections
    await alice.connect(bob)
    await alice.connect(charlie)

    # Traverse network
    analyzer = NetworkAnalyzer()
    await analyzer.spawn(alice)

    print(f"Processed users: {analyzer.processed_users}")
    print(f"Analysis results: {analyzer.response}")

if __name__ == "__main__":
    asyncio.run(main())
```

### FastAPI Server Integration Example

**Complete REST API with automatic documentation**

```python
import asyncio
from jvspatial.api import Server, walker_endpoint
from jvspatial.api.endpoint_router import EndpointField
from jvspatial.core import Node, Walker, on_visit

class Product(Node):
    name: str = ""
    price: float = 0.0
    category: str = ""
    in_stock: bool = True

# Create server
server = Server(
    title="Product Management API",
    description="Manage products with graph-based relationships",
    version="1.0.0"
)

@walker_endpoint("/api/products/search", methods=["POST"])
class SearchProducts(Walker):
    """Search products with advanced filtering."""

    category: str = EndpointField(
        description="Product category to search",
        examples=["electronics", "books", "clothing"]
    )

    min_price: float = EndpointField(
        default=0.0,
        description="Minimum price filter",
        ge=0.0
    )

    max_price: float = EndpointField(
        default=10000.0,
        description="Maximum price filter",
        ge=0.0
    )

    @on_visit(Node)
    async def search_products(self, here: Node):
        # MongoDB-style query with filters
        products = await Product.find({
            "$and": [
                {"context.category": self.category},
                {"context.price": {"$gte": self.min_price, "$lte": self.max_price}},
                {"context.in_stock": True}
            ]
        })

        self.response = {
            "products": [
                {
                    "id": p.id,
                    "name": p.name,
                    "price": p.price,
                    "category": p.category
                } for p in products
            ],
            "total_found": len(products),
            "filters_applied": {
                "category": self.category,
                "price_range": [self.min_price, self.max_price]
            }
        }

async def setup_sample_data():
    """Create sample product data."""
    products = [
        {"name": "Laptop Pro", "price": 1299.99, "category": "electronics"},
        {"name": "Python Book", "price": 39.99, "category": "books"},
        {"name": "Gaming Mouse", "price": 79.99, "category": "electronics"},
        {"name": "T-Shirt", "price": 19.99, "category": "clothing"}
    ]

    for product_data in products:
        await Product.create(**product_data)

    print(f"Created {len(products)} sample products")

@server.on_startup
async def initialize_data():
    """Initialize sample data on server startup."""
    await setup_sample_data()

if __name__ == "__main__":
    server.run()  # API available at http://localhost:8000/docs
```

**API Usage:**
```bash
# Search for electronics under $100
curl -X POST "http://localhost:8000/api/products/search" \
  -H "Content-Type: application/json" \
  -d '{
    "category": "electronics",
    "min_price": 0,
    "max_price": 100
  }'
```

## Object Pagination Example

**Efficient handling of large datasets**

```python
import asyncio
from jvspatial.core import Node
from jvspatial.core.pager import ObjectPager, paginate_objects

class Customer(Node):
    name: str = ""
    email: str = ""
    signup_date: str = ""
    plan: str = "free"
    active: bool = True

async def pagination_example():
    # Create sample customers
    customer_data = [
        {"name": f"Customer {i}", "email": f"user{i}@company.com",
         "plan": "premium" if i % 3 == 0 else "free"}
        for i in range(100)
    ]

    for data in customer_data:
        await Customer.create(**data)

    # Simple pagination
    first_page = await paginate_objects(Customer, page=1, page_size=20)
    print(f"First page: {len(first_page)} customers")

    # Advanced pagination with filtering
    pager = ObjectPager(
        Customer,
        page_size=25,
        filters={"context.plan": "premium"},
        order_by="name",
        order_direction="asc"
    )

    premium_customers = await pager.get_page(1)
    print(f"Premium customers: {len(premium_customers)}")

    # Process all pages efficiently
    page_count = 0
    total_processed = 0

    while True:
        customers = await pager.next_page()
        if not customers:
            break

        page_count += 1
        total_processed += len(customers)

        print(f"Processed page {page_count}: {len(customers)} customers")

        # Process customers in batch
        for customer in customers:
            # Simulate processing
            pass

    print(f"Total processed: {total_processed} customers")

if __name__ == "__main__":
    asyncio.run(pagination_example())
```

## Advanced MongoDB-Style Query Examples

**Complex queries with multiple operators**

```python
import asyncio
from jvspatial.core import Node

class Employee(Node):
    name: str = ""
    department: str = ""
    salary: float = 0.0
    skills: list[str] = []
    hire_date: str = ""
    active: bool = True

async def query_examples():
    # Create sample employees
    employees = [
        {"name": "Alice", "department": "engineering", "salary": 95000, "skills": ["python", "javascript"], "active": True},
        {"name": "Bob", "department": "engineering", "salary": 87000, "skills": ["java", "python"], "active": True},
        {"name": "Charlie", "department": "marketing", "salary": 65000, "skills": ["analytics"], "active": True},
        {"name": "Diana", "department": "engineering", "salary": 102000, "skills": ["go", "rust"], "active": False}
    ]

    for emp_data in employees:
        await Employee.create(**emp_data)

    # Complex query: Active high-paid engineers with Python skills
    senior_python_devs = await Employee.find({
        "$and": [
            {"context.department": "engineering"},
            {"context.salary": {"$gte": 90000}},
            {"context.skills": {"$in": ["python"]}},
            {"context.active": True}
        ]
    })

    print(f"Senior Python developers: {len(senior_python_devs)}")

    # Text search with regex
    name_search = await Employee.find({
        "context.name": {"$regex": "^A", "$options": "i"}
    })

    print(f"Names starting with 'A': {len(name_search)}")

    # Range queries
    mid_salary_range = await Employee.find({
        "context.salary": {
            "$gte": 70000,
            "$lte": 100000
        }
    })

    print(f"Mid-salary range employees: {len(mid_salary_range)}")

    # Count and distinct operations
    eng_count = await Employee.count({"context.department": "engineering"})
    all_departments = await Employee.distinct("department")

    print(f"Engineers: {eng_count}")
    print(f"Departments: {all_departments}")

if __name__ == "__main__":
    asyncio.run(query_examples())
```

## Testing Patterns

**Isolated testing with entity-centric operations**

```python
import pytest
import asyncio
from jvspatial.core import Node

class TestUser(Node):
    name: str = ""
    email: str = ""
    role: str = "user"

# Test entity CRUD operations
@pytest.mark.asyncio
async def test_user_crud():
    """Test basic CRUD operations."""
    # Create
    user = await TestUser.create(
        name="Test User",
        email="test@example.com",
        role="admin"
    )
    assert user.name == "Test User"
    assert user.role == "admin"

    # Read
    retrieved = await TestUser.get(user.id)
    assert retrieved.email == "test@example.com"

    # Update
    user.role = "moderator"
    await user.save()

    updated = await TestUser.get(user.id)
    assert updated.role == "moderator"

    # Delete
    await user.delete()
    deleted = await TestUser.get(user.id)
    assert deleted is None

@pytest.mark.asyncio
async def test_mongodb_queries():
    """Test MongoDB-style query operations."""
    # Setup test data
    users = [
        {"name": "Alice", "email": "alice@test.com", "role": "admin"},
        {"name": "Bob", "email": "bob@test.com", "role": "user"},
        {"name": "Charlie", "email": "charlie@test.com", "role": "user"}
    ]

    created_users = []
    for user_data in users:
        user = await TestUser.create(**user_data)
        created_users.append(user)

    # Query tests
    admins = await TestUser.find({"context.role": "admin"})
    assert len(admins) == 1
    assert admins[0].name == "Alice"

    # Regex query
    a_names = await TestUser.find({
        "context.name": {"$regex": "^A", "$options": "i"}
    })
    assert len(a_names) == 1

    # Count operation
    user_count = await TestUser.count({"context.role": "user"})
    assert user_count == 2

    # Cleanup
    for user in created_users:
        await user.delete()

if __name__ == "__main__":
    # Run tests
    asyncio.run(test_user_crud())
    asyncio.run(test_mongodb_queries())
    print("All tests passed!")
```

## Running Examples

Save any of the above examples as Python files and run them:

```bash
# Basic entity operations
python entity_crud_example.py

# Walker traversal
python walker_example.py

# FastAPI server
python server_example.py
# Then visit http://localhost:8000/docs

# Object pagination
python pagination_example.py

# MongoDB-style queries
python query_example.py

# Testing
python test_example.py
```

## Key Features Demonstrated

These examples showcase jvspatial's core capabilities:

- **Entity-Centric Design**: Clean, intuitive APIs for working with graph data
- **MongoDB-Style Queries**: Familiar query syntax across all database backends
- **Object Pagination**: Efficient handling of large datasets
- **Walker Traversal**: Powerful graph traversal with semantic filtering
- **FastAPI Integration**: Automatic REST API endpoints with OpenAPI docs
- **Async Architecture**: Native async/await support throughout
- **Testing-Friendly**: Simple patterns for isolated testing

For more detailed documentation, see:
- [MongoDB-Style Query Interface](mongodb-query-interface.md)
- [Object Pagination Guide](pagination.md)
- [REST API Integration](rest-api.md)
- [GraphContext & Database Management](graph-context.md)

1. **Clean Dependency Injection**: No scattered database connections across classes
2. **Testing Isolation**: Easy to create isolated test environments
3. **Configuration Flexibility**: Switch databases without changing entity code
4. **Backward Compatibility**: Existing API (`Node.create()`, `Edge.create()`) works unchanged
5. **Explicit Control**: When needed, full control over database operations

For more details, see [GraphContext Documentation](./graph-context.md).
