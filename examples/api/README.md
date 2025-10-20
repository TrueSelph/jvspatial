# API Examples

This directory contains examples showcasing the jvspatial API capabilities. Most API examples are now in the `examples/server` directory, which contains more comprehensive examples of API server functionality.

Please refer to `examples/server/README.md` for detailed API examples, including:

- Server configuration and setup
- Endpoint decoration
- Response handling
- Error management
- Dynamic endpoint registration
- FastAPI integration

## Authenticated Endpoints

### authenticated_endpoints_example.py

Demonstrates how to use authentication decorators to create secure API endpoints:

**Decorators covered:**
- `@auth_endpoint` - Authenticated endpoints (for both functions and Walker classes)
- `@admin_endpoint` - Admin-only endpoints (for both functions and Walker classes)

**Features demonstrated:**
- Role-based access control (RBAC)
- Permission-based access control
- Combining roles and permissions
- Multiple authentication patterns
- Walker graph traversal with authentication
- Proper naming conventions (`here` for visited nodes)

**Key concepts:**
- Authentication decorators automatically handle auth validation
- Middleware integration for credential checking
- Role checking: user must have AT LEAST ONE required role
- Permission checking: user must have ALL required permissions
- Proper error responses (401 Unauthorized, 403 Forbidden)

**Usage:**
```python
from jvspatial.api import auth_endpoint
from jvspatial.core import Node, Walker, on_visit

# Simple authenticated endpoint
@auth_endpoint("/api/profile", methods=["GET"])
async def get_profile(endpoint):
    return endpoint.success(data={"profile": "data"})

# Endpoint with permissions
@auth_endpoint("/api/data", permissions=["read_data"])
async def read_data(endpoint):
    return endpoint.success(data={"data": "protected"})

# Endpoint with roles
@auth_endpoint("/api/report", roles=["analyst", "admin"])
async def generate_report(endpoint):
    return endpoint.success(data={"report": "generated"})

# Walker endpoint with authentication
@auth_endpoint("/api/analyze", permissions=["analyze_data"])
class AnalyzeWalker(Walker):
    @on_visit(Node)
    async def analyze(self, here: Node):
        # Process authenticated graph traversal
        self.report({"analyzed": here.id})
```

**Important notes:**
- The example demonstrates decorator usage only
- For a working server, authentication middleware must be configured
- Users must be created with appropriate roles and permissions
- See the example file for complete setup instructions

Run the example:
```bash
python authenticated_endpoints_example.py
```

Note: The example will display information about the decorators but won't start a server by default. Uncomment `server.run()` to start the server (requires full auth setup).
