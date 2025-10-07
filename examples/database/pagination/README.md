# Database Pagination Examples

This directory contains examples demonstrating pagination features:

- `object_pagination_demo.py` - Object-based pagination patterns

## Features

### Object Pagination
- Cursor-based pagination
- Offset/limit pagination
- Page size control
- Sorting support
- Performance considerations

## Usage

```python
from examples.database.pagination.object_pagination_demo import paginated_query

# Get first page
results, cursor = await paginated_query(limit=10)

# Get next page using cursor
next_results, next_cursor = await paginated_query(cursor=cursor, limit=10)
```