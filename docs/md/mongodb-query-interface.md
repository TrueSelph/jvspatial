# MongoDB-Style Query Interface

The jvspatial library provides a unified **MongoDB-style query interface** that works consistently across all database backends. This allows you to use familiar MongoDB query syntax regardless of whether you're using JSON files, MongoDB, or custom database implementations.

## Overview

The query interface provides:

- **Consistent Syntax**: MongoDB-style queries work across all database backends
- **Native Optimization**: MongoDB uses native queries while other databases use the standardized parser
- **Comprehensive Operators**: Support for comparison, logical, array, and string operators
- **Entity-Centric Integration**: Works seamlessly with `Node.find()`, `User.find()`, etc.
- **Dot Notation**: Support for nested field queries using `context.field` notation

## Basic Query Structure

All queries in jvspatial follow MongoDB query syntax:

```python
from jvspatial.core import Node

class User(Node):
    name: str = ""
    email: str = ""
    age: int = 0
    department: str = ""
    active: bool = True
    skills: list[str] = []

# Simple equality query
users = await User.find({"context.name": "Alice"})

# Complex query with operators
results = await User.find({
    "context.age": {"$gte": 25, "$lt": 65},
    "context.department": {"$in": ["engineering", "product"]},
    "$or": [
        {"context.active": True},
        {"context.skills": {"$in": ["python", "javascript"]}}
    ]
})
```

## Comparison Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$eq` | Equal to | `{"context.age": {"$eq": 30}}` |
| `$ne` | Not equal to | `{"context.status": {"$ne": "inactive"}}` |
| `$gt` | Greater than | `{"context.age": {"$gt": 18}}` |
| `$gte` | Greater than or equal | `{"context.score": {"$gte": 80}}` |
| `$lt` | Less than | `{"context.price": {"$lt": 1000}}` |
| `$lte` | Less than or equal | `{"context.quantity": {"$lte": 10}}` |
| `$in` | Value in array | `{"context.category": {"$in": ["A", "B"]}}` |
| `$nin` | Value not in array | `{"context.status": {"$nin": ["deleted"]}}` |

### Examples

```python
# Find users older than 35
senior_users = await User.find({"context.age": {"$gte": 35}})

# Find users younger than 30
young_users = await User.find({"context.age": {"$lt": 30}})

# Find non-admin users
non_admin_users = await User.find({"context.role": {"$ne": "admin"}})

# Find users in specific departments
dept_users = await User.find({
    "context.department": {"$in": ["engineering", "marketing", "sales"]}
})

# Find users not in certain departments
other_users = await User.find({
    "context.department": {"$nin": ["temp", "contractor"]}
})
```

## Logical Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$and` | Logical AND | `{"$and": [{"a": 1}, {"b": 2}]}` |
| `$or` | Logical OR | `{"$or": [{"a": 1}, {"b": 2}]}` |
| `$not` | Logical NOT | `{"$not": {"age": {"$lt": 18}}}` |
| `$nor` | Logical NOR | `{"$nor": [{"a": 1}, {"b": 2}]}` |

### Examples

```python
# AND conditions - active engineering users
engineers = await User.find({
    "$and": [
        {"context.department": "engineering"},
        {"context.active": True}
    ]
})

# OR conditions - senior users or managers
senior_or_manager = await User.find({
    "$or": [
        {"context.age": {"$gte": 40}},
        {"context.role": "manager"}
    ]
})

# NOT conditions - users not in temp status
permanent_users = await User.find({
    "$not": {"context.status": "temporary"}
})

# Complex nested logic
complex_query = await User.find({
    "$and": [
        {"context.active": True},
        {
            "$or": [
                {"context.department": "engineering"},
                {"context.skills": {"$in": ["python", "javascript"]}}
            ]
        }
    ]
})
```

## Array Operations

| Operator | Description | Example |
|----------|-------------|---------|
| `$in` | Value in array | `{"context.skills": {"$in": ["python", "js"]}}` |
| `$nin` | Value not in array | `{"context.skills": {"$nin": ["java"]}}` |
| `$all` | All elements match | `{"context.tags": {"$all": ["red", "blue"]}}` |
| `$size` | Array size | `{"context.tags": {"$size": 3}}` |
| `$elemMatch` | Element matches condition | `{"context.items": {"$elemMatch": {"qty": {"$gt": 20}}}}` |

### Examples

```python
# Users with Python or JavaScript skills
tech_users = await User.find({
    "context.skills": {"$in": ["python", "javascript"]}
})

# Users without Java skills
non_java_users = await User.find({
    "context.skills": {"$nin": ["java", "c++"]}
})

# Users with all specified skills
full_stack = await User.find({
    "context.skills": {"$all": ["python", "javascript", "sql"]}
})

# Users with exactly 3 skills
balanced_users = await User.find({
    "context.skills": {"$size": 3}
})
```

## String Operations

| Operator | Description | Example |
|----------|-------------|---------|
| `$regex` | Regular expression | `{"context.name": {"$regex": "^John", "$options": "i"}}` |
| `$options` | Regex options | Used with `$regex` for case-insensitive matching |

### Examples

```python
# Case-insensitive name search
johnson_family = await User.find({
    "context.name": {"$regex": "Johnson", "$options": "i"}
})

# Email domain filtering
company_emails = await User.find({
    "context.email": {"$regex": "@company\\.com$", "$options": "i"}
})

# Names starting with 'A'
a_names = await User.find({
    "context.name": {"$regex": "^A", "$options": "i"}
})
```

## Element Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `$exists` | Field exists | `{"context.email": {"$exists": true}}` |
| `$type` | Field type | `{"context.count": {"$type": "int"}}` |

### Examples

```python
# Users with email addresses
users_with_email = await User.find({
    "context.email": {"$exists": True}
})

# Users without phone numbers
users_no_phone = await User.find({
    "context.phone": {"$exists": False}
})
```

## Complex Query Examples

### Multi-Condition Filtering

```python
# Active senior engineers with Python skills
active_senior_engineers = await User.find({
    "$and": [
        {"context.department": "engineering"},
        {"context.age": {"$gte": 35}},
        {"context.active": True},
        {"context.skills": {"$in": ["python", "go", "rust"]}}
    ]
})
```

### Range Queries

```python
# Mid-career professionals
mid_career = await User.find({
    "context.experience_years": {
        "$gte": 3,
        "$lte": 10
    }
})

# Salary range filtering
salary_range = await User.find({
    "context.salary": {
        "$gte": 50000,
        "$lt": 150000
    }
})
```

### Text Search Patterns

```python
# Multiple name variations
name_search = await User.find({
    "$or": [
        {"context.name": {"$regex": "john", "$options": "i"}},
        {"context.email": {"$regex": "john", "$options": "i"}},
        {"context.username": {"$regex": "john", "$options": "i"}}
    ]
})

# Domain-specific searches
tech_domains = await User.find({
    "context.email": {
        "$regex": "@(google|apple|microsoft)\\.com$",
        "$options": "i"
    }
})
```

## Integration with Entity Methods

The MongoDB-style query interface integrates seamlessly with jvspatial's entity-centric methods:

### Core Entity Methods

```python
# Standard find with MongoDB queries
users = await User.find({
    "context.department": "engineering",
    "context.active": True
})

# Find one user
user = await User.find_one({
    "context.email": "alice@company.com"
})

# Count with filtering
count = await User.count({
    "context.department": "engineering"
})

# Get distinct values
departments = await User.distinct("department")
```

### Walker Integration

```python
from jvspatial.core import Walker, on_visit

class UserAnalyzer(Walker):
    @on_visit(User)
    async def analyze_user(self, here: User):
        # Use MongoDB-style queries during traversal
        colleagues = await User.find({
            "context.department": here.department,
            "context.active": True,
            "context.id": {"$ne": here.id}  # Exclude current user
        })

        # Process colleagues
        self.response[here.id] = {
            "name": here.name,
            "colleagues_count": len(colleagues)
        }
```

### Semantic Filtering with nodes()

```python
# Use MongoDB-style queries for semantic filtering during traversal
engineering_users = await user.nodes(
    node=[{'User': {"context.department": "engineering"}}],
    active=True  # Additional simple filtering
)

# Complex filtering with multiple conditions
experienced_users = await user.nodes(
    node=[{
        'User': {
            "$and": [
                {"context.experience_years": {"$gte": 5}},
                {"context.skills": {"$in": ["python", "javascript"]}}
            ]
        }
    }]
)
```

## Database Backend Compatibility

The MongoDB-style query interface works consistently across all backends:

### JSON Database
- Queries are parsed and executed in-memory
- Full operator support through query engine
- Suitable for development and small datasets

### MongoDB Database
- Queries are passed directly to MongoDB
- Native optimization and indexing
- Best performance for production use

### Custom Databases
- Implement query parsing in your database class
- Use provided query utilities for consistency
- Maintain compatibility with standard interface

## Best Practices

### 1. Use Proper Field Prefixes

```python
# Good: Use context prefix for entity fields
users = await User.find({"context.name": "Alice"})

# Bad: Direct field access (may not work consistently)
users = await User.find({"name": "Alice"})
```

### 2. Leverage Database Indexes

```python
# Good: Query commonly indexed fields
users = await User.find({"context.email": "alice@company.com"})

# Consider indexing strategies for frequently queried fields
```

### 3. Optimize Complex Queries

```python
# Good: Specific conditions first
efficient_query = await User.find({
    "context.department": "engineering",  # Specific filter first
    "context.active": True,
    "context.skills": {"$in": ["python"]}
})

# Good: Use appropriate operators
range_query = await User.find({
    "context.age": {"$gte": 25, "$lte": 65}
})
```

### 4. Handle Edge Cases

```python
# Check for existence before complex operations
users_with_skills = await User.find({
    "$and": [
        {"context.skills": {"$exists": True}},
        {"context.skills": {"$in": ["python", "javascript"]}}
    ]
})
```

## Error Handling

```python
try:
    users = await User.find({
        "context.age": {"$gte": 25},
        "context.department": {"$in": ["engineering", "product"]}
    })

    if not users:
        print("No users found matching criteria")

except Exception as e:
    print(f"Query error: {e}")
```


The MongoDB-style query interface in jvspatial provides a powerful, consistent way to work with your graph data across any database backend, making it easy to build complex applications with familiar syntax.

## See Also

- [Entity Reference](entity-reference.md) - Complete API reference including query methods
- [Object Pagination Guide](pagination.md) - Using queries with pagination
- [Examples](examples.md) - Query examples and patterns
- [GraphContext & Database Management](graph-context.md) - Database integration
- [REST API Integration](rest-api.md) - Using queries in API endpoints

---

**[← Back to README](../../README.md)** | **[Entity Reference →](entity-reference.md)**
