# Logging Examples

This directory contains examples demonstrating the jvspatial logging system.

## Custom Log Levels

### Overview

jvspatial supports custom log levels beyond the standard Python logging levels (DEBUG, INFO, WARNING, ERROR, CRITICAL). This allows you to categorize logs with domain-specific severity levels like AUDIT, SECURITY, TRACE, or CUSTOM.

### Pre-registered Levels

jvspatial pre-registers a `CUSTOM` log level at level 25 (between INFO=20 and WARNING=30) that you can use immediately.

### Examples

#### [`custom_log_levels_example.py`](custom_log_levels_example.py)

Comprehensive example showing:
- How to use the pre-registered CUSTOM level
- How to register additional custom log levels (TRACE, AUDIT, SECURITY)
- Using custom levels with standard Python logging
- Using custom levels with JVSpatialLogger
- Using custom levels with BaseLoggingService
- Configuring DBLogHandler to capture custom levels
- Querying custom level logs from the database

**Run the example:**

```bash
python examples/logging/custom_log_levels_example.py
```

### Quick Start

#### 1. Use the Pre-registered CUSTOM Level

The simplest way to use custom logging:

```python
import logging
from jvspatial.logging import initialize_logging_database, CUSTOM_LEVEL_NUMBER

# Initialize database logging to capture CUSTOM level
initialize_logging_database(
    log_levels={CUSTOM_LEVEL_NUMBER, logging.ERROR, logging.CRITICAL}
)

# Use it with standard logging
logger = logging.getLogger(__name__)
logger.custom("This is a custom log message")

# Or with JVSpatialLogger
from jvspatial.logging import get_logger
jv_logger = get_logger(__name__)
jv_logger.custom("Custom log with context", user_id="user_123")
```

#### 2. Register Your Own Custom Levels

For domain-specific log levels:

```python
from jvspatial.logging import add_custom_log_level, initialize_logging_database

# Register custom levels
AUDIT = add_custom_log_level("AUDIT", 35, "audit")
SECURITY = add_custom_log_level("SECURITY", 45, "security")
TRACE = add_custom_log_level("TRACE", 5, "trace")

# Configure database logging to capture them
initialize_logging_database(
    log_levels={TRACE, AUDIT, SECURITY, logging.ERROR, logging.CRITICAL}
)

# Use them
import logging
logger = logging.getLogger(__name__)
logger.audit("User action audited", extra={"user_id": "user_123"})
logger.security("Security event", extra={"threat_level": "high"})
logger.trace("Detailed trace information")
```

#### 3. Use with BaseLoggingService

Direct database logging with custom levels:

```python
from jvspatial.logging import get_logging_service

service = get_logging_service()

# Use log_custom() for CUSTOM level
await service.log_custom(
    event_code="custom_event",
    message="Custom event message",
    details={"key": "value"}
)

# Or use log_error() with log_level parameter for any custom level
await service.log_error(
    event_code="audit_event",
    message="Audit trail entry",
    log_level="AUDIT",
    details={"action": "data_export"}
)
```

#### 4. Query Custom Level Logs

Retrieve logs by custom level:

```python
from jvspatial.logging import get_logging_service

service = get_logging_service()

# Get all CUSTOM level logs
custom_logs = await service.get_error_logs(log_level="CUSTOM")

# Get all AUDIT level logs
audit_logs = await service.get_error_logs(log_level="AUDIT")

# Combine with other filters
security_logs = await service.get_error_logs(
    log_level="SECURITY",
    start_time=datetime.now() - timedelta(hours=24),
    page=1,
    page_size=50
)
```

### Log Level Guidelines

When choosing level numbers for custom levels:

- **CRITICAL (50)**: System-wide critical failures
- **SECURITY (45)**: Security-related events (custom)
- **ERROR (40)**: Error conditions
- **AUDIT (35)**: Audit trail events (custom)
- **WARNING (30)**: Warning conditions
- **CUSTOM (25)**: General custom events (pre-registered)
- **INFO (20)**: Informational messages
- **DEBUG (10)**: Debug information
- **TRACE (5)**: Detailed trace information (custom)
- **NOTSET (0)**: Not set

### Best Practices

1. **Choose Meaningful Names**: Use names that reflect your domain (AUDIT, SECURITY, BUSINESS_EVENT, etc.)

2. **Choose Appropriate Numbers**: Place custom levels between standard levels based on their importance

3. **Document Your Levels**: Document what each custom level means in your application

4. **Be Consistent**: Use the same custom levels across your application

5. **Configure Capture Levels**: Remember to include custom levels in the `log_levels` parameter when initializing the database handler

6. **Index by Level**: The `log_level` field is indexed in the database, so querying by custom level is efficient

### API Reference

#### `add_custom_log_level(level_name, level_number, method_name=None)`

Register a new custom log level.

- **level_name** (str): Name of the level (e.g., "AUDIT")
- **level_number** (int): Numeric value for the level
- **method_name** (str, optional): Method name to add to Logger class (defaults to level_name.lower())

Returns the level number.

#### `get_custom_levels()`

Get all registered custom log levels.

Returns a set of custom level names.

#### `is_custom_level(level_name)`

Check if a log level is a custom level.

- **level_name** (str): Name of the level to check

Returns True if the level is a custom level.

#### `CUSTOM_LEVEL_NUMBER`

The pre-registered CUSTOM level number (25).

### Additional Resources

- [Database Logging Documentation](../../docs/md/database-logging.md) (if exists)
- [jvspatial Logging Documentation](../../jvspatial/logging/__init__.py)
- [Python Logging Documentation](https://docs.python.org/3/library/logging.html)

