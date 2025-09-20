# MongoDB-style Query Interface

The jvspatial library provides a unified MongoDB-style query interface that works consistently across all database backends. This allows you to use familiar MongoDB query syntax regardless of whether you're using JSON files, MongoDB, or custom database implementations.

## Overview

The query interface provides:

- **Consistent Syntax**: MongoDB-style queries work across all database backends
- **Native Optimization**: MongoDB uses native queries while other databases use the standardized parser
- **Comprehensive Operators**: Support for comparison, logical, array, and string operators
- **Enhanced Methods**: find_one, count, distinct, update, delete operations
- **Query Builder**: Programmatic query construction
- **Dot Notation**: Support for nested field queries

## Basic Query Structure

All queries in jvspatial follow MongoDB query syntax:

```python
from jvspatial.db import get_database

# Get database instance
db = get_database("json")  # or "mongodb", or custom database

# Simple equality query
results = await db.find("collection", {"field": "value"})

# Complex query with operators
results = await db.find("collection", {
    "price": {"$gt": 100, "$lt": 500},
    "category": {"$in": ["electronics", "books"]},
    "$or": [
        {"in_stock": True},
        {"featured": True}
    ]
})
```

## Query Operators

### Comparison Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$eq` | Equal to | `{"price": {"$eq": 100}}` |
| `$ne` | Not equal to | `{"status": {"$ne": "inactive"}}` |
| `$gt` | Greater than | `{"age": {"$gt": 18}}` |
| `$gte` | Greater than or equal | `{"score": {"$gte": 80}}` |
| `$lt` | Less than | `{"price": {"$lt": 1000}}` |
| `$lte` | Less than or equal | `{"quantity": {"$lte": 10}}` |
| `$in` | Value in array | `{"category": {"$in": ["A", "B"]}}` |
| `$nin` | Value not in array | `{"status": {"$nin": ["deleted"]}}` |

### Logical Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$and` | Logical AND | `{"$and": [{"a": 1}, {"b": 2}]}` |
| `$or` | Logical OR | `{"$or": [{"a": 1}, {"b": 2}]}` |
| `$not` | Logical NOT | `{"$not": {"age": {"$lt": 18}}}` |
| `$nor` | Logical NOR | `{"$nor": [{"a": 1}, {"b": 2}]}` |

### Element Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$exists` | Field exists | `{"email": {"$exists": true}}` |
| `$type` | Field type | `{"count": {"$type": "int"}}` |

### Array Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$size` | Array size | `{"tags": {"$size": 3}}` |
| `$all` | All elements match | `{"tags": {"$all": ["red", "blue"]}}` |
| `$elemMatch` | Element matches condition | `{"items": {"$elemMatch": {"qty": {"$gt": 20}}}}` |

### String Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$regex` | Regular expression | `{"name": {"$regex": "^John", "$options": "i"}}` |

### Evaluation Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$mod` | Modulo operation | `{"qty": {"$mod": [4, 0]}}` |

## Enhanced Query Methods

### find_one()

Find the first document matching a query:

```python
# Find first expensive item
result = await db.find_one("products", {"price": {"$gt": 1000}})
if result:
    print(f"Found: {result['name']} (${result['price']})")
```

### count()

Count documents matching a query:

```python
# Count electronics
count = await db.count("products", {"category": "electronics"})
print(f"Found {count} electronics")

# Count all documents
total = await db.count("products")
```

### distinct()

Get distinct values for a field:

```python
# Get all categories
categories = await db.distinct("products", "category")
print(f"Categories: {categories}")

# Get distinct values with query filter
active_categories = await db.distinct("products", "category", {"active": True})
```

### update_one() and update_many()

Update documents with MongoDB-style update operations:

```python
# Update single document
result = await db.update_one(
    "products",
    {"name": "Laptop Pro"},                    # filter
    {"$set": {"price": 1299.99, "sale": True}} # update
)

# Update multiple documents
result = await db.update_many(
    "products",
    {"category": "electronics"},     # filter
    {"$inc": {"views": 1}}          # increment views
)

# Upsert (insert if not found)
result = await db.update_one(
    "products",
    {"sku": "ABC123"},
    {"$set": {"name": "New Product", "price": 99.99}},
    upsert=True
)
```

### delete_one() and delete_many()

Delete documents matching a query:

```python
# Delete single document
result = await db.delete_one("products", {"name": "Old Product"})

# Delete multiple documents
result = await db.delete_many("products", {"discontinued": True})
```

## Update Operations

MongoDB-style update operators are supported:

### Field Update Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$set` | Set field value | `{"$set": {"price": 100}}` |
| `$unset` | Remove field | `{"$unset": {"oldField": ""}}` |
| `$inc` | Increment value | `{"$inc": {"views": 1}}` |
| `$mul` | Multiply value | `{"$mul": {"price": 1.1}}` |

### Array Update Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$push` | Add to array | `{"$push": {"tags": "new"}}` |
| `$pull` | Remove from array | `{"$pull": {"tags": "old"}}` |

## Query Builder

For complex queries, use the programmatic query builder:

```python
from jvspatial.db import query

# Build complex query
q = (query()
     .field("category").eq("electronics")
     .field("price").gte(50).lte(200)
     .field("in_stock").eq(True)
     .build())

results = await db.find("products", q)

# Logical operations
q = (query()
     .or_(
         {"category": "electronics"},
         {"featured": True}
     )
     .build())

# Field operations
q = (query()
     .field("tags").size(3)
     .field("rating").gte(4.0)
     .field("description").regex("premium", "i")
     .build())
```

## Dot Notation

Access nested fields using dot notation:

```python
# Query nested fields
results = await db.find("users", {
    "profile.age": {"$gte": 21},
    "address.city": "San Francisco",
    "preferences.notifications.email": True
})

# Array indexing
results = await db.find("orders", {
    "items.0.name": "Laptop",  # First item name
    "tags.1": "electronics"   # Second tag
})
```

## Working with jvspatial Nodes

When querying jvspatial Node objects, remember that field data is stored in the `context` field:

```python
from jvspatial.core import Node, GraphContext

class Product(Node):
    name: str = ""
    price: float = 0.0
    category: str = ""

# Create context and products
ctx = GraphContext(database=db)
laptop = await ctx.create(Product, name="MacBook Pro", price=2499, category="electronics")

# Query the nodes - use context.fieldname
electronics = await db.find("node", {"context.category": "electronics"})
expensive = await db.find("node", {"context.price": {"$gt": 2000}})

# Update operations
await db.update_many(
    "node",
    {"context.category": "electronics"},
    {"$inc": {"context.price": 100}}  # Increase all electronics prices
)
```

## Database-Specific Optimizations

### MongoDB Native Queries

When using MongoDB, queries are passed directly to the database for optimal performance:

```python
# These queries run natively in MongoDB
results = await mongodb.find("collection", {
    "$text": {"$search": "laptop"},
    "price": {"$gte": 500},
    "$and": [
        {"category": "electronics"},
        {"$or": [{"sale": True}, {"featured": True}]}
    ]
})
```

### Custom Database Integration

Custom databases use the standardized query parser:

```python
from jvspatial.db import Database, matches_query

class CustomDatabase(Database):
    async def find(self, collection: str, query: Dict[str, Any]):
        results = []
        for doc in self.get_all_docs(collection):
            # Use standardized query matcher
            if matches_query(doc, query):
                results.append(doc)
        return results
```

## Performance Tips

1. **Use Indexes**: Create indexes on frequently queried fields
2. **Limit Results**: Use `find_one()` when you only need the first result
3. **Specific Queries**: More specific queries perform better than broad ones
4. **Native MongoDB**: Use MongoDB for complex queries requiring native operators

## Error Handling

```python
try:
    results = await db.find("collection", {"invalid_field": {"$invalidOp": "value"}})
except Exception as e:
    print(f"Query error: {e}")

# Safe counting
count = await db.count("collection", query) or 0

# Safe distinct values
values = await db.distinct("collection", "field") or []
```

## Examples

### E-commerce Product Queries

```python
# Find products in price range
products = await db.find("products", {
    "price": {"$gte": 50, "$lte": 200},
    "category": "electronics",
    "in_stock": True
})

# Find products with specific tags
tagged_products = await db.find("products", {
    "tags": {"$all": ["wireless", "bluetooth"]}
})

# Find sale items or featured items
special_products = await db.find("products", {
    "$or": [
        {"on_sale": True},
        {"featured": True},
        {"rating": {"$gte": 4.5}}
    ]
})
```

### User Management Queries

```python
# Find active users over 18
adults = await db.find("users", {
    "$and": [
        {"age": {"$gte": 18}},
        {"status": "active"},
        {"profile.verified": True}
    ]
})

# Find users by location
local_users = await db.find("users", {
    "address.state": "CA",
    "address.city": {"$in": ["San Francisco", "Los Angeles"]}
})
```

### Analytics Queries

```python
# Count by category
categories = await db.distinct("products", "category")
for category in categories:
    count = await db.count("products", {"category": category})
    print(f"{category}: {count} products")

# Find recent activity
recent = await db.find("activities", {
    "timestamp": {"$gte": datetime.now() - timedelta(days=7)},
    "type": {"$in": ["login", "purchase", "view"]}
})
```

The unified MongoDB-style query interface provides powerful, flexible querying capabilities while maintaining consistency across all database backends in jvspatial.