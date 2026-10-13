# API architecture

jvspatial's [`Server`](../../jvspatial/api/server.py) composes FastAPI app
construction, endpoint registration, middleware, lifecycle and the database
context. Applications use the public `jvspatial.api` exports; implementation
mixins and component paths are maintainer references, not import contracts.

## Configuration and server lifecycle

`Server` accepts configuration through
[`ServerConfig`](../../jvspatial/api/config.py) and its grouped settings in
[`config_groups.py`](../../jvspatial/api/config_groups.py). Database, auth, CORS,
security, file storage and scheduler options follow those schemas. Environment
adaptation uses the declared `JVSPATIAL_*` allowlist rather than arbitrary
configuration keys.

[`server_app_factory.py`](../../jvspatial/api/server_app_factory.py),
[`server_registration.py`](../../jvspatial/api/server_registration.py),
[`server_lifecycle.py`](../../jvspatial/api/server_lifecycle.py) and
[`server_run.py`](../../jvspatial/api/server_run.py) implement the composition.
The [`LifecycleManager`](../../jvspatial/api/services/lifecycle.py) integrates
startup and shutdown with FastAPI lifespan.

See [Server API](server-api.md) for supported configuration and hooks, and
[Production Deployment](production-deployment.md) for production requirements.

## Endpoint discovery and routing

The public `@endpoint` decorator supports functions and Walker classes.
It records declarations in the
[deferred registry](../../jvspatial/api/decorators/deferred_registry.py);
Server registration resolves those declarations into routes. Applications
should follow the [Endpoint Registration Guide](endpoint-registration-guide.md)
for construction and module-import ordering.

```python
from jvspatial.api import Server, endpoint

@endpoint("/ready", methods=["GET"], auth=False)
async def ready() -> dict:
    return {"state": "ready"}

server = Server(title="Example API", db_type="json", db_path="./data")

if __name__ == "__main__":
    server.run()
```

The explicitly public readiness route does not demonstrate authenticated
production deployment. Set authentication and route permissions for your
application's actual requirements.

The current routing implementation lives in [`endpoints/`](../../jvspatial/api/endpoints/):

- [`registry.py`](../../jvspatial/api/endpoints/registry.py) tracks endpoint declarations.
- [`factory.py`](../../jvspatial/api/endpoints/factory.py) builds routes and validation.
- [`router.py`](../../jvspatial/api/endpoints/router.py) contains the router surface.
- [`response.py`](../../jvspatial/api/endpoints/response.py) provides `ResponseHelper`
  and `format_response`, exported through `jvspatial.api`.

Use [Decorator Reference](decorator-reference.md) for field and endpoint
parameters and [REST API](rest-api.md) for request/response examples.

## Authentication and middleware

Authentication implementation lives in
[`auth/service.py`](../../jvspatial/api/auth/service.py),
[`auth/models.py`](../../jvspatial/api/auth/models.py) and
[`auth/rbac.py`](../../jvspatial/api/auth/rbac.py). User, API-key, session and
refresh-token state belongs to the prime database. Access checks do not move
to a secondary logging database.

[`ServerConfigurator`](../../jvspatial/api/server_configurator.py) installs
request context, rate limiting, authentication and exception handlers.
[`MiddlewareManager`](../../jvspatial/api/middleware/manager.py) configures
security headers, CORS and optional/custom middleware. FastAPI executes HTTP
middleware in reverse registration order.

The [authentication middleware](../../jvspatial/api/components/auth_middleware.py)
enforces declared auth, roles and permissions. Raw FastAPI routes may delegate
authentication only to an enforcing `SecurityBase` dependency; a function name
or an arbitrary `Depends` declaration does not prove authentication. Auth
entrypoint limits remain independent of the global rate limiter.

See [Authentication](authentication.md), [API Keys](api-keys.md),
[Rate Limiting](rate-limiting.md) and [Security Operational Notes](security-operational-notes.md).

## Context and transactions

[`ServerContext`](../../jvspatial/api/context.py), `get_current_server` and
`set_current_server` bind the active server. `GraphContext` binds entity
persistence to its database, cache and monitor. Applications must keep
workspace/access policy separate from context selection: a context is a
persistence boundary, not an authorization grant.

Multi-write atomic entity/edge work uses [Transactions](transactions.md),
with native backend qualification and transaction-local cache isolation.
See [Context Management](context-management-guide.md) for scoped context usage.

## Optional integrations

- [Webhooks](webhook-architecture.md):
  [`integrations/webhooks/`](../../jvspatial/api/integrations/webhooks/).
- Scheduling: [`integrations/scheduler/`](../../jvspatial/api/integrations/scheduler/)
  and the [runnable scheduler examples](../../examples/scheduler/README.md).
- File storage: [File Storage Usage](file-storage-usage.md) and
  [File Storage Architecture](file-storage-architecture.md).

Internal integration classes and directory names can evolve. Use public Server,
decorator and configuration contracts when integrating an application.
