# jvspatial API Examples

This directory contains **standard reference implementations** for building custom jvspatial APIs. These examples serve as the recommended starting point for all jvspatial API development.

## 🎯 Standard Implementation Examples

### 1. **Authenticated Endpoints Example** ⭐
📁 **File**: [`authenticated_endpoints_example.py`](authenticated_endpoints_example.py)

**Complete CRUD API with authentication and authorization**

This is the **standard example** for building authenticated APIs with jvspatial. It demonstrates:

- ✅ Complete CRUD operations (Create, Read, Update, Delete)
- ✅ JWT-based authentication (`auth_enabled=True`)
- ✅ **Automatic authentication endpoints** (`/auth/register`, `/auth/login`, `/auth/logout`)
- ✅ Permission and role-based access control
- ✅ Entity-centric database operations
- ✅ Pagination with `ObjectPager`
- ✅ Response schemas with examples
- ✅ Walker-based analytics endpoints

**When to use**: Build your authenticated API using this as a template.

**Run it**:
```bash
python examples/api/authenticated_endpoints_example.py
```

**Access**: `http://127.0.0.1:8000/docs`

### 2. **Unauthenticated Endpoints Example** ⭐
📁 **File**: [`unauthenticated_endpoints_example.py`](unauthenticated_endpoints_example.py)

**Public read-only API without authentication**

This is the **standard example** for building public/unauthenticated APIs with jvspatial. It demonstrates:

- ✅ Public endpoints (no authentication required)
- ✅ Read-only operations (GET endpoints)
- ✅ Listing with pagination and filtering
- ✅ Entity-centric retrieval operations
- ✅ Response schemas with examples
- ✅ **No authentication endpoints** (`auth_enabled=False` means `/auth/*` routes are NOT registered)

**When to use**: Build your public API or read-only service using this as a template.

**Run it**:
```bash
python examples/api/unauthenticated_endpoints_example.py
```

**Access**: `http://127.0.0.1:8000/docs`

## Key Differences

| Feature | Authenticated Example | Unauthenticated Example |
|---------|----------------------|------------------------|
| **Authentication** | ✅ Enabled (`auth_enabled=True`) | ❌ Disabled (`auth_enabled=False`) |
| **Auth Endpoints** | ✅ Automatically registered (`/auth/register`, `/auth/login`, `/auth/logout`) | ❌ **NOT registered** |
| **Operations** | Create, Read, Update, Delete | Read only (GET endpoints) |
| **Access Control** | Permission and role-based | Public (no access control) |
| **Use Case** | Private/protected APIs | Public content APIs |

## Implementation Patterns

Both examples demonstrate the following **standard patterns**:

### 1. Entity-Centric Operations
```python
# ✅ Standard pattern
user = await UserNode.get(user_id)
users = await UserNode.find(query)
user = await UserNode.create(name="John", email="john@example.com")
await user.save()
await user.delete()
```

### 2. Pagination
```python
# ✅ Standard pattern
pager = ObjectPager(UserNode, page_size=per_page)
users = await pager.get_page(page=page)
pagination_info = pager.to_dict()
return {"users": [user.export() for user in users], **pagination_info}
```

### 3. Response Schemas
```python
# ✅ Standard pattern
@endpoint(
    "/users",
    methods=["GET"],
    response=success_response(
        data={
            "users": ResponseField(List[Dict[str, Any]], "List of users", example=[...]),
            "total": ResponseField(int, "Total count", example=100),
        }
    )
)
```

### 4. Export Pattern
```python
# ✅ Standard pattern
return {"user": user.export()}  # Automatically handles transient fields
```

## Documentation

For detailed documentation on API implementation standards, see:

- **[API Implementation Standards](../../docs/md/API_IMPLEMENTATION_STANDARDS.md)** - Comprehensive guide
- **[Examples Documentation](../../docs/md/examples.md)** - All available examples
- **[REST API Guide](../../docs/md/rest-api.md)** - API design patterns
- **[Server API Guide](../../docs/md/server-api.md)** - Server configuration

## Quick Reference

### Starting a New Authenticated API

1. Copy `authenticated_endpoints_example.py` as your starting point
2. Modify the data models (`UserNode`, `ProductNode`, etc.)
3. Customize the endpoints to match your domain
4. Adjust permissions and roles as needed
5. Run and test at `http://127.0.0.1:8000/docs`

### Starting a New Public API

1. Copy `unauthenticated_endpoints_example.py` as your starting point
2. Modify the data models (`ArticleNode`, `BookNode`, etc.)
3. Customize the endpoints to match your domain
4. Add filtering and pagination as needed
5. Run and test at `http://127.0.0.1:8000/docs`

## Other Examples

This directory also contains additional example files for specific use cases:

- `diagnostic_auth_swagger.py` - Diagnostic tools for authentication

For more examples covering other jvspatial features, see the main [examples directory](../README.md).
