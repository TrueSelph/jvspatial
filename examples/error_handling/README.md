# Error Handling Examples

This directory contains examples demonstrating best practices for error handling in jvspatial applications.

## Examples

### 🛡️ Basic Error Handling (`basic_error_handling.py`)
Demonstrates fundamental error handling patterns:
- Entity operation errors
- Validation errors
- General error handling patterns
- Error context and details

### 🔌 Database Error Handling (`database_error_handling.py`)
Shows robust database error handling:
- Connection errors and retries
- Query error handling
- Transaction safety
- Fallback strategies
- Database configuration errors

### 🚶 Walker Error Handling (`walker_error_handling.py`)
Demonstrates Walker-specific error handling:
- Walker execution errors
- Timeout handling
- Node processing errors
- Retry mechanisms
- Error reporting strategies

## Key Concepts

### Exception Hierarchy
All jvspatial exceptions inherit from `JVSpatialError`:
```python
from jvspatial.exceptions import (
    JVSpatialError,         # Base exception
    EntityNotFoundError,    # Entity lookup failures
    DatabaseError,          # Database operation failures
    WalkerExecutionError,   # Walker runtime errors
)
```

**Note**: Pydantic validation errors are raised as `pydantic.ValidationError`, not `jvspatial.exceptions.ValidationError`. Import it separately:
```python
from pydantic import ValidationError as PydanticValidationError
```

### Best Practices
1. **Use Specific Exceptions**: Catch specific exceptions before general ones
```python
from pydantic import ValidationError as PydanticValidationError

try:
    result = await operation()
except PydanticValidationError as e:
    # Handle Pydantic validation error
    for error in e.errors():
        field = ".".join(str(loc) for loc in error.get("loc", []))
        print(f"{field}: {error.get('msg')}")
except EntityNotFoundError as e:
    # Handle not found error
except JVSpatialError as e:
    # Handle any other jvspatial error
```

2. **Entity Not Found Handling**: `Object.get()` returns `None` if not found, doesn't raise exception
```python
user = await User.get(user_id)
if user is None:
    raise EntityNotFoundError(
        entity_type="User",
        entity_id=user_id,
        details={"message": "User not found"}
    )
```

3. **Error Context**: Access error details when available
```python
except EntityNotFoundError as e:
    print(f"Error: {e.message}")
    print(f"Entity type: {e.entity_type}, ID: {e.entity_id}")
    if e.details:
        print(f"Details: {e.details}")
```

4. **Graceful Degradation**: Implement fallback strategies
```python
from jvspatial.db.factory import create_database

try:
    db = create_database("mongodb", uri="mongodb://localhost:27017")
except (ConnectionError, ValueError):
    # Fallback to JSON database
    db = create_database("json", base_path="./jvdb")
```

5. **Safe Transactions**: Use try/except in database operations
```python
try:
    await entity.save()
except DatabaseError as e:
    await handle_rollback()
```

6. **Walker Safety**: Handle walker-specific errors
```python
try:
    await walker.spawn(root)
except WalkerTimeoutError as e:
    partial_results = walker.get_report()
```

## Running Examples

Run any example directly with Python:

```bash
# Basic error handling
python examples/error_handling/basic_error_handling.py

# Database error handling
python examples/error_handling/database_error_handling.py

# Walker error handling
python examples/error_handling/walker_error_handling.py
```

## Related Documentation
- [Error Handling Guide](../../docs/md/error-handling.md)
- [Database Configuration](../../docs/md/configuration.md)
- [Walker Patterns](../../docs/md/walker-patterns.md)