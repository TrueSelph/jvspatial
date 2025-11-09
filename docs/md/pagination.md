# Object Pagination in jvspatial

The jvspatial core module provides comprehensive pagination support through the `ObjectPager` class and convenient helper functions. This enables efficient handling of large graphs and datasets by allowing you to process objects (including nodes, edges, and custom objects) in manageable chunks without loading everything into memory.

## Overview

Pagination in jvspatial operates at the database level, ensuring optimal performance even with millions of objects. The pagination system supports:

- **Database-level filtering**: Queries execute at the database level for maximum efficiency
- **Flexible filtering**: Support for complex filter conditions and field-based pagination
- **Type safety**: Returns properly typed node instances
- **Memory efficiency**: Process large graphs without memory overload
- **Easy-to-use API**: Simple functions alongside the full-featured ObjectPager class

## Quick Start

### Simple Object Pagination

```python
from jvspatial.core import paginate_objects, City

# Get first page of cities (default: 20 per page)
cities = await paginate_objects(City)
print(f"Found {len(cities)} cities")

# Get specific page with custom page size
cities_page_2 = await paginate_objects(City, page=2, page_size=50)
```

### Field-Based Pagination

```python
from jvspatial.core import paginate_by_field, City

# Paginate cities ordered by population (largest first)
populous_cities = await paginate_by_field(
    City,
    field="population",
    order="desc",
    page_size=25
)
```

### Advanced Pagination with Filters

```python
from jvspatial.core import ObjectPager, City

# Create pager with custom filters
pager = ObjectPager(
    City,
    page_size=100,
    filters={"population": {"$gt": 1000000}}  # Only cities > 1M population
)

# Get results
large_cities = await pager.get_page()
print(f"Found {len(large_cities)} large cities")

# Check if more pages available
if pager.has_next_page():
    next_cities = await pager.next_page()
```

## ObjectPager Class

The `ObjectPager` class provides full-featured pagination with filtering, ordering, and page navigation.

### Constructor

```python
from jvspatial.core import ObjectPager

pager = ObjectPager(
    City,                    # Object class to paginate
    page_size=50,            # Results per page (default: 20)
    filters=None,            # Optional database filters
    order_by=None,           # Field to order by
    order_direction="asc"    # "asc" or "desc"
)
```

### Parameters

- **object_class**: The Object class to paginate through
- **page_size**: Number of results per page (default: 20)
- **filters**: Dictionary of database-level filters to apply
- **order_by**: Field name to sort results by
- **order_direction**: Sort direction - "asc" (default) or "desc"

### Methods

#### `get_page(page: int = 1) -> List[Object]`
Get a specific page of results:

```python
# Get first page
first_page = await pager.get_page(1)

# Get specific page
third_page = await pager.get_page(3)
```

#### `next_page() -> List[Object]`
Get the next page of results:

```python
pager = ObjectPager(City, page_size=25)

# Get first page
page1 = await pager.next_page()  # Gets page 1
page2 = await pager.next_page()  # Gets page 2
page3 = await pager.next_page()  # Gets page 3
```

#### `previous_page() -> List[Object]`
Get the previous page of results:

```python
# Move forward then back
await pager.next_page()  # Page 1
await pager.next_page()  # Page 2
previous = await pager.previous_page()  # Back to page 1
```

#### Properties

```python
# Current page number (1-based)
current_page = pager.current_page

# Check if more pages are available
if pager.has_next_page():
    print("More pages available")

if pager.has_previous_page():
    print("Previous pages available")

# Check if results were cached
if pager.is_cached:
    print("Results came from cache")
```

## Helper Functions

### `paginate_objects()`

Simple pagination for object types:

```python
async def paginate_objects(
    object_type: Type[Object],
    page: int = 1,
    page_size: int = 20,
    filters: Optional[dict] = None
) -> List[Object]
```

**Example Usage:**

```python
from jvspatial.core import paginate_objects, Person

# Basic pagination
people = await paginate_objects(Person, page=1, page_size=50)

# With filters
adults = await paginate_objects(
    Person,
    page=1,
    page_size=25,
    filters={"age": {"$gte": 18}}
)
```

### `paginate_by_field()`

Field-based pagination with ordering:

```python
async def paginate_by_field(
    object_type: Type[Object],
    field: str,
    page: int = 1,
    page_size: int = 20,
    order: str = "asc",
    filters: Optional[dict] = None
) -> List[Object]
```

**Example Usage:**

```python
from jvspatial.core import paginate_by_field, Product

# Get products ordered by price (lowest first)
cheap_products = await paginate_by_field(
    Product,
    field="price",
    order="asc",
    page_size=30
)

# Get highest-rated products with filters
top_electronics = await paginate_by_field(
    Product,
    field="rating",
    order="desc",
    page_size=20,
    filters={"category": "electronics"}
)
```

## Advanced Examples

### Processing Large Datasets

Process large graphs efficiently by combining pagination with async processing:

```python
from jvspatial.core import ObjectPager, User
import asyncio

async def process_all_users():
    """Process all users in batches."""
    pager = ObjectPager(User, page_size=100)

    while True:
        # Get next batch
        users = await pager.next_page()
        if not users:
            break

        # Process batch in parallel
        tasks = [process_user(user) for user in users]
        await asyncio.gather(*tasks)

        print(f"Processed page {pager.current_page}")

async def process_user(user):
    """Process individual user."""
    # Perform user analysis/updates
    user.last_processed = datetime.now()
    await user.save()
```

### Complex Filtering

Use database-level filters for efficient queries:

```python
from jvspatial.core import ObjectPager, Order

# Complex filter example
pager = ObjectPager(
    Order,
    page_size=50,
    filters={
        "status": {"$in": ["pending", "processing"]},
        "total": {"$gte": 100.0},
        "created_at": {"$gte": "2023-01-01"}
    },
    order_by="created_at",
    order_direction="desc"
)

# Get recent high-value pending orders
important_orders = await pager.get_page()
```

### Memory-Efficient Graph Traversal

Combine pagination with walker traversal for large graphs:

```python
from jvspatial.core import ObjectPager, Walker, on_visit, City

class CityAnalyzer(Walker):
    """Analyzes cities in paginated batches."""

    def __init__(self):
        super().__init__()
        self.analyzed_count = 0

    async def analyze_all_cities(self):
        """Analyze all cities using pagination."""
        pager = ObjectPager(City, page_size=25)

        while True:
            cities = await pager.next_page()
            if not cities:
                break

            # Visit each city in the batch
            await self.visit(cities)

    @on_visit(City)
    async def analyze_city(self, here: City):
        """Analyze individual city."""
        self.analyzed_count += 1

        # Perform analysis
        neighbors = await here.neighbors(limit=5)
        self.response[here.id] = {
            "population": here.population,
            "connections": len(neighbors)
        }
```

### Data Export with Pagination

Export large datasets efficiently:

```python
import json
from jvspatial.core import ObjectPager, Customer

async def export_customers_to_json(filename: str):
    """Export all customers to JSON file."""
    pager = ObjectPager(Customer, page_size=100)

    all_customers = []

    while True:
        customers = await pager.next_page()
        if not customers:
            break

        # Convert to serializable format
        for customer in customers:
            all_customers.append({
                "id": customer.id,
                "name": customer.name,
                "email": customer.email,
                "created_at": customer.created_at
            })

        print(f"Exported {len(all_customers)} customers so far...")

    # Write to file
    with open(filename, 'w') as f:
        json.dump(all_customers, f, indent=2)

    print(f"Exported {len(all_customers)} total customers to {filename}")
```

## Performance Considerations

### Database-Level Filtering

Always use database filters rather than Python filtering:

```python
# Good: Database-level filtering
large_cities = await paginate_objects(
    City,
    filters={"population": {"$gt": 1000000}}
)

# Bad: Python-level filtering (loads all data)
all_cities = await City.all()
large_cities = [c for c in all_cities if c.population > 1000000]
```

### Optimal Page Sizes

Choose page sizes based on your use case:

```python
# Small pages for interactive UIs
ui_pager = ObjectPager(Product, page_size=20)

# Medium pages for processing workflows
processing_pager = ObjectPager(Order, page_size=100)

# Large pages for bulk operations
bulk_pager = ObjectPager(LogEntry, page_size=1000)
```

### Memory Management

Monitor memory usage in long-running pagination:

```python
import gc
from jvspatial.core import ObjectPager, LargeDataNode

async def process_large_dataset():
    """Process very large dataset with memory management."""
    pager = ObjectPager(LargeDataNode, page_size=50)

    page_count = 0
    while True:
        nodes = await pager.next_page()
        if not nodes:
            break

        # Process nodes
        for node in nodes:
            await process_node(node)

        page_count += 1

        # Periodic garbage collection
        if page_count % 10 == 0:
            gc.collect()
            print(f"Processed {page_count * 50} nodes")
```

### Index Optimization

Ensure your database has appropriate indexes for filtered fields:

```python
# If frequently paginating by these fields, ensure database indexes exist:
# - population (for range queries)
# - created_at (for date ordering)
# - status (for equality filters)

efficient_pager = ObjectPager(
    User,
    filters={"status": "active", "last_login": {"$gte": "2023-01-01"}},
    order_by="created_at"  # Should have index
)
```

## Best Practices

### 1. Use Appropriate Page Sizes

```python
# Interactive UI: Small pages
ui_results = await paginate_objects(Product, page_size=20)

# Batch processing: Medium pages
await process_in_batches(Order, page_size=100)

# Bulk operations: Large pages
bulk_export = await paginate_objects(LogEntry, page_size=500)
```

### 2. Leverage Database Filtering

```python
# Push filtering to database level
filtered_pager = ObjectPager(
    Customer,
    filters={
        "subscription_tier": {"$in": ["premium", "enterprise"]},
        "active": True
    }
)
```

### 3. Combine with Caching

```python
from jvspatial.core import ObjectPager
import asyncio

class CachedPagination:
    def __init__(self, object_type, page_size=50):
        self.pager = ObjectPager(object_type, page_size)
        self.cache = {}

    async def get_cached_page(self, page_num):
        """Get page with caching."""
        if page_num not in self.cache:
            self.cache[page_num] = await self.pager.get_page(page_num)
        return self.cache[page_num]
```

### 4. Error Handling

```python
async def safe_pagination(object_type, **kwargs):
    """Paginate with error handling."""
    try:
        pager = ObjectPager(object_type, **kwargs)
        return await pager.get_page()
    except Exception as e:
        print(f"Pagination error: {e}")
        return []
```

### 5. Progress Tracking

```python
async def paginate_with_progress(object_type, page_size=100):
    """Paginate with progress reporting."""
    pager = ObjectPager(object_type, page_size)
    total_processed = 0

    while True:
        nodes = await pager.next_page()
        if not nodes:
            break

        total_processed += len(nodes)
        print(f"Progress: Page {pager.current_page}, "
              f"Total processed: {total_processed}")

        yield nodes
```

## Integration Examples

### With FastAPI

```python
from fastapi import FastAPI, Query
from jvspatial.core import paginate_objects, Product

app = FastAPI()

@app.get("/products")
async def get_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str = None
):
    filters = {}
    if category:
        filters["category"] = category

    products = await paginate_objects(
        Product,
        page=page,
        page_size=page_size,
        filters=filters
    )

    return {
        "page": page,
        "page_size": page_size,
        "products": [p.export() for p in products]
    }
```

### With Data Processing Pipelines

```python
from jvspatial.core import ObjectPager, Customer

async def customer_analytics_pipeline():
    """Run analytics on all customers in batches."""
    pager = ObjectPager(Customer, page_size=200)
    analytics_results = []

    while True:
        customers = await pager.next_page()
        if not customers:
            break

        # Process batch
        batch_analytics = await analyze_customer_batch(customers)
        analytics_results.extend(batch_analytics)

        print(f"Completed page {pager.current_page}")

    return analytics_results

async def analyze_customer_batch(customers):
    """Analyze a batch of customers."""
    results = []
    for customer in customers:
        # Perform customer analysis
        result = {
            "customer_id": customer.id,
            "lifetime_value": await calculate_lifetime_value(customer),
            "segment": await determine_segment(customer)
        }
        results.append(result)
    return results
```

The pagination system in jvspatial provides a powerful, efficient way to handle large datasets while maintaining the library's semantic simplicity and performance optimization principles.

## See Also

- [Entity Reference](entity-reference.md) - Complete API reference including ObjectPager
- [MongoDB-Style Query Interface](mongodb-query-interface.md) - Query syntax for filters
- [Examples](examples.md) - Pagination examples and patterns
- [GraphContext & Database Management](graph-context.md) - Database integration
- [REST API Integration](rest-api.md) - Using pagination in APIs

---

**[← Back to README](../../README.md)** | **[Entity Reference →](entity-reference.md)**
