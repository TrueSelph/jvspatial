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
    ValidationError,        # Data validation errors
    EntityNotFoundError,    # Entity lookup failures
    DatabaseError,          # Database operation failures
    WalkerExecutionError,   # Walker runtime errors
)
```

### Best Practices
1. **Use Specific Exceptions**: Catch specific exceptions before general ones
```python
try:
    result = await operation()
except ValidationError as e:
    # Handle validation error
except EntityNotFoundError as e:
    # Handle not found error
except JVSpatialError as e:
    # Handle any other jvspatial error
```

2. **Error Context**: Access error details when available
```python
except ValidationError as e:
    print(f"Error: {e.message}")
    if e.field_errors:
        for field, error in e.field_errors.items():
            print(f"{field}: {error}")
```

3. **Graceful Degradation**: Implement fallback strategies
```python
try:
    db = await setup_primary_database()
except ConnectionError:
    db = await setup_fallback_database()
```

4. **Safe Transactions**: Use try/except in database operations
```python
try:
    await entity.save()
except DatabaseError as e:
    await handle_rollback()
```

5. **Walker Safety**: Handle walker-specific errors
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