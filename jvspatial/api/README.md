# jvspatial/api

FastAPI integration: `Server` class, endpoint decorator, auth, middleware, and lifecycle.

> **Read first**: [SPEC §8-10](../../SPEC.md), [docs/md/api-architecture.md](../../docs/md/api-architecture.md)

---

## Purpose

`api/` adapts the entity layer to FastAPI. The `Server` class composes app construction, route registration, lifecycle, and uvicorn invocation. `@endpoint` turns functions or Walker classes into HTTP routes with consistent auth, validation, and response shaping.

## Layout

```
api/
├── server.py                 # Server (composition of 4 mixins)
├── server_app_factory.py     # AppFactoryMixin (internal)
├── server_registration.py    # RegistrationMixin (internal)
├── server_lifecycle.py       # LifecycleMixin (internal)
├── server_run.py             # RunMixin (internal)
├── config.py                 # ServerConfig (Pydantic)
├── config_groups.py          # DatabaseConfig, AuthConfig, etc.
├── context.py                # ServerContext + per-request helpers
├── exceptions.py             # APIError hierarchy
├── auth/                     # JWT, API keys, RBAC, sessions
├── components/               # AppBuilder, AuthConfigurator, middleware
├── decorators/               # @endpoint, deferred registry, endpoint fields
├── endpoints/                # Registry, factory, router, response
├── integrations/             # Webhooks, scheduler, storage service
├── middleware/               # Rate limit, manager
├── services/                 # Endpoint discovery
└── utils/                    # Misc helpers
```

## Public API (from `jvspatial.api`)

| Name | What it does |
|---|---|
| `Server` | Main server class (SPEC §8.1) |
| `create_server` | Functional constructor |
| `ServerConfig` | Pydantic config (SPEC §10.1) |
| `ServerContext`, `get_current_server`, `set_current_server` | Per-request server binding |
| `get_auth_service` | Singleton accessor for `AuthenticationService` |
| `@endpoint` | Unified function / Walker route decorator (SPEC §8.2) |
| `BaseRouter`, `EndpointRouter` | Mountable routers |
| `endpoint_field`, `EndpointField`, `EndpointFieldInfo` | Endpoint parameter helpers |
| `format_response`, `ResponseHelper` | Response shaping |
| `register_deferred_endpoint`, `flush_deferred_endpoints`, `get_deferred_endpoint_count`, `clear_deferred_endpoints`, `sync_endpoint_modules` | Deferred-registry utilities (SPEC §8.3) |

## Invariants

- **Auth state lives on the prime database only.** Users, sessions, API keys, refresh tokens, password-reset tokens — all on prime DB. Not relocatable. (`auth/service.py`)
- **JWT secret is required when auth is enabled.** Server fails fast with a clear error if `JVSPATIAL_JWT_SECRET_KEY` is empty or a placeholder. (`auth/service.py`, [CHANGELOG 0.0.7](../../CHANGELOG.md))
- **All secret comparisons use `hmac.compare_digest`.** No `==` for tokens, keys, or hashes.
- **CORS defaults are restrictive.** Wildcards must be explicit and trigger a startup warning. (`components/cors_configurator.py`)
- **CSP is strict on app routes, relaxed only on `/docs`, `/redoc`, `/openapi.json`.** (`components/app_builder.py`)
- **`JVSPATIAL_DOCS_DISABLED` removes the entire docs surface.** No spec leak when truthy. (`components/app_builder.py`)
- **Sessions and rate-limit counters are per-process.** Multi-worker deployments multiply configured limits by worker count.
- **Endpoint registration is deferred.** `@endpoint` collects targets at import; `Server` resolves them at app build time.

## Modification patterns

- Adding a new endpoint kind: extend `decorators/route.py` and update `endpoints/factory.py`. New decorator forms must be auth/role/webhook-aware.
- Adding new middleware: register via `Server.middleware_manager.add(...)`. Built-ins live in `middleware/` and `components/`.
- Adding a new auth flow: extend `auth/service.py` and `auth/rbac.py`. Add a security-review entry per [docs/md/security-review.md](../../docs/md/security-review.md).
- Adding a new lifecycle hook: declare in `Server` constructor signature, wire through `LifecycleMixin`, document under [docs/md/server-api.md](../../docs/md/server-api.md).

## Related docs

- [docs/md/api-architecture.md](../../docs/md/api-architecture.md)
- [docs/md/server-api.md](../../docs/md/server-api.md)
- [docs/md/endpoint-registration-guide.md](../../docs/md/endpoint-registration-guide.md)
- [docs/md/decorator-reference.md](../../docs/md/decorator-reference.md)
- [docs/md/authentication.md](../../docs/md/authentication.md)
- [docs/md/api-keys.md](../../docs/md/api-keys.md)
- [docs/md/auth-quickstart.md](../../docs/md/auth-quickstart.md)
- [docs/md/rate-limiting.md](../../docs/md/rate-limiting.md)
- [docs/md/webhook-architecture.md](../../docs/md/webhook-architecture.md)

## Stability

Public names listed above are stable. The `server_*` mixin modules are internal — assemble through `Server` only. `components/`, `middleware/`, `services/`, and `integrations/` internals can change between minor versions; cross them only through the public surface.
