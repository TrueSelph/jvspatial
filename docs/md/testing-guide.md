# Testing Guide

This guide covers testing jvspatial applications, including the Request State Contract for in-process auth testing.

## Test Auth Mode

When using ASGI in-process testing (e.g. `TestClient` or httpx `ASGITransport`), enable `test_mode=True` in auth config. The auth middleware will then honor a pre-set `request.state.user` (with an `id` attribute) and skip authentication. Use a test fixture or middleware that runs before the auth middleware to inject the test user.

## Request State Contract

The authentication middleware uses `request.state.user` as the standard contract:

- **`request.state.user`** is set by `AuthenticationMiddleware` after successful authentication (JWT or API key)
- When `test_mode=True`, the middleware honors a pre-set `request.state.user` if it has an `id` attribute
- Endpoints receive `user_id` or `current_user` via parameter injection from `request.state.user`

## Isolated Test Databases

Use SQLite `:memory:` for fast, isolated tests:

```python
import pytest
from jvspatial.core.context import GraphContext
from jvspatial.db import create_database

@pytest.fixture
async def test_context():
    db = create_database(db_type="sqlite", db_path=":memory:")
    return GraphContext(database=db)
```

## Bootstrap Admin for Tests

Use `AuthenticationService.bootstrap_admin()` to create an admin user when needed:

```python
from jvspatial.api.auth.service import AuthenticationService
from jvspatial.core.context import GraphContext
from jvspatial.db import create_database, get_database_manager

async def setup_test_auth():
    db = create_database(db_type="sqlite", db_path=":memory:")
    manager = get_database_manager()
    manager.set_prime_database(db)
    ctx = GraphContext(database=db)
    auth_service = AuthenticationService(ctx, jwt_secret="test-secret")
    admin = await auth_service.bootstrap_admin("admin@test.com", "password123", "Test Admin")
    return ctx, auth_service, admin
```

## See Also

- [Authentication](authentication.md) - Request State Contract details
- [Graph Context](graph-context.md) - Test database setup
