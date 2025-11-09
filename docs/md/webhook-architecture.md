# JVspatial Webhook Architecture Specification

## Overview

This document outlines the architecture for the webhook endpoint system in jvspatial built around the unified `@webhook_endpoint` decorator. This decorator automatically detects whether it's decorating a function or Walker class, extending the existing `@endpoint` pattern to support webhook-specific functionality while maintaining consistency in registration, metadata-driven authentication, and server integration.

The system registers GET/POST routes for incoming webhook payloads, supports optional authentication via permissions and roles (checked by existing middleware), and incorporates webhook standards compliance including HTTPS enforcement, HMAC signature verification, idempotency keys, asynchronous processing, robust error handling (always acknowledging receipt with HTTP 200), and retry mechanisms.

### @webhook_endpoint (Unified Decorator)

The `@webhook_endpoint` decorator works with both function-based webhook handlers and Walker classes for graph traversal. It automatically detects the target type and applies the appropriate configuration.

**For Function-Based Handlers:**

**Signature:**
```python
@webhook_endpoint(
    path: str,
    *,
    methods: List[str] = ["POST"],  # GET or POST for webhooks
    permissions: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    hmac_secret: Optional[str] = None,  # Shared secret for HMAC verification
    idempotency_key_field: str = "X-Idempotency-Key",  # Header/field for idempotency
    idempotency_ttl_hours: int = 24,  # TTL for idempotency records
    async_processing: bool = False,  # Queue for async handling
    server: Optional[Server] = None,
    **route_kwargs: Any  # Additional FastAPI route params (e.g., tags, summary)
)
```

**Behavior:**
- Stores webhook metadata on the function: `_webhook_required=True`, `_hmac_secret`, `_idempotency_key_field`, `_idempotency_ttl_hours`, `_async_processing`.
- Inherits auth metadata: `_auth_required=True` (if permissions/roles provided), `_required_permissions`, `_required_roles`.
- Registers as a custom route in `server._custom_routes` (similar to `auth_endpoint`), with a wrapper that injects an `endpoint` helper and handles webhook preprocessing.
- If server unavailable (e.g., during module import), defers registration.

**Example:**
```python
from jvspatial.api.webhook.decorators import webhook_endpoint

@webhook_endpoint(
    "/webhook/payment",
    permissions=["process_payments"],
    hmac_secret="my-webhook-secret",
    async_processing=True
)
async def handle_payment_webhook(payload: dict, endpoint):
    # payload is verified JSON from request.body
    # Process payment event
    return endpoint.success(
        message="Payment processed",
        data={"status": "processed"}
    )
```

**For Walker-Based Handlers (Graph Traversal):**

The same `@webhook_endpoint` decorator detects Walker classes automatically. The signature and parameters are identical.

**Behavior:**
- Stores metadata on the Walker class: `_webhook_required=True`, `_is_webhook=True`, plus webhook and auth fields
- Registers via `server.register_walker_class(walker_class, path, methods)`, with webhook wrapper
- Walker instances receive `payload` in their context (e.g., `self.payload`), enabling graph updates based on webhook data

**Example:**
```python
from jvspatial.core.entities import Walker, on_visit, Node
from jvspatial.api.webhook.decorators import webhook_endpoint

@webhook_endpoint(
    "/webhook/location-update",
    roles=["user"],
    hmac_secret="location-secret"
)
class LocationUpdateWalker(Walker):
    payload: dict  # Webhook data injected here

    @on_visit(Node)
    async def update_location(self, here: Node):
        # Update node with location from self.payload
        here.location = self.payload.get("coordinates")
        await here.save()
        self.response["updated"] = True
```

**Note:** The decorator automatically detects if the target is a Walker class (using `inspect.isclass()` and `issubclass(target, Walker)`) and applies the appropriate handler logic. No need for separate decorators!

## Server Integration

Leverage existing `Server` from `jvspatial/api/server.py`:

- **Registration:** Use `_custom_routes` for functions (add POST route with webhook wrapper). For walkers, `register_walker_class` with path prefix `/webhooks`.
- **Dynamic Support:** If server running (`_is_running=True`), add routes dynamically via `app.add_api_route` or new dynamic router.
- **Discovery:** Extend package discovery in `discover_and_register_packages` to detect `@webhook_*` via `_jvspatial_webhook_config`.
- **Path Prefix:** All webhook routes under `/webhooks` (configurable via server config).

## Middleware Pipeline

Insert `WebhookMiddleware` early in the FastAPI middleware stack (before `AuthenticationMiddleware`):

1. **HTTPS Enforcement:** Check `request.url.scheme == "https"`. If not and `require_https=True` (server config), raise 403.
2. **HMAC Verification:** If `_hmac_secret`, compute HMAC-SHA256 of `request.body` using secret, compare to `X-HMAC-Signature` header. Raise 401 on mismatch.
3. **Idempotency Check:** Extract key from `_idempotency_key_field` (header or payload). Query DB (new `webhook_events` collection in GraphContext) for processed key (TTL via `_idempotency_ttl_hours`). If exists, return 200 with cached response. Else, mark as processing.
4. **Payload Parsing:** Validate JSON `request.body`, inject as `request.state.payload: dict`.
5. **Async Processing:** If `_async_processing`, queue task (e.g., via `asyncio.create_task` or external queue like Celery) and return 200 immediately. Store task ID for retries.
6. **Proceed to Auth:** Pass to `AuthenticationMiddleware` for permissions/roles check using stored metadata.
7. **Endpoint Execution:** Call handler with `payload` arg.

**New Utilities:**
- `verify_hmac(payload: bytes, signature: str, secret: str) -> bool`: Computes and compares HMAC.
- `check_idempotency(ctx: GraphContext, key: str, ttl_hours: int) -> Optional[Dict]`: Queries/inserts idempotency record (use Node/Edge for events).
- `queue_webhook_task(server: Server, handler: Callable, payload: dict) -> str`: Queues async, returns task ID.

## Response Handling

Webhook endpoints use the standard `EndpointResponseHelper` methods. This provides:

- **Consistency:** Same response patterns across all endpoint types (`@endpoint`, `@webhook_endpoint`, `@walker_endpoint`, etc.)
- **Standard HTTP Status Codes:** Automatic status code handling via `endpoint.success()` (200), `endpoint.bad_request()` (400), `endpoint.server_error()` (500), etc.
- **Unified Error Handling:** No separate webhook error handling logic needed
- **Parameter Injection:** Improved parameter injection handles both `payload: dict` and raw payload parameters based on function signature


## Payload Processing and Triggering

- **Functions:** Wrapper injects `payload: dict` and `endpoint` helper. Handler: `async def handler(payload: dict, endpoint)` returns standard endpoint responses via `endpoint.success()`, `endpoint.bad_request()`, etc.
- **Walkers:** Create instance with `Walker(payload=payload)`, inject into graph walk. Access via `self.payload`. Response via `self.response`.
- **Error Handling:** Catch exceptions in wrapper, log (with task ID for retries), return 200 `{ "status": "received", "task_id": "..." }`. Store error in DB for retry queue.
- **Retries:** Exponential backoff (e.g., 5 attempts). Failed tasks trigger email/Slack alerts (configurable).

## Standards Compliance

- **HTTPS:** Enforced in middleware; redirect HTTP to HTTPS in production.
- **HMAC:** Supports `X-HMAC-Signature` (hex-encoded SHA256). Secret per-endpoint or global.
- **Idempotency:** Uses unique keys; stores minimal receipt (status, timestamp) to avoid duplicates.
- **Async:** Non-blocking; suitable for long-running graph updates.
- **Error Handling:** Always 200 on receipt; detailed errors in body only if sync and safe.
- **Retries:** Webhook sender retries on non-2xx; system supports via task queue.

## Security Considerations

- Secrets: Store in env vars or server config; rotate periodically.
- Rate Limiting: Integrate with existing `RateLimiter` using IP or idempotency key.
- Payload Size: Limit to 1MB; validate schema if needed (future Pydantic integration).
- Logging: Sanitize sensitive payload fields (e.g., PII).

## Example Usage in Server

```python
from jvspatial.api.server import Server

server = Server(title="JVspatial Webhook API")
# Decorators auto-register on import

# Add middleware
server.app.add_middleware(WebhookMiddleware, exempt_paths=["/health"])
server.app.add_middleware(AuthenticationMiddleware)

server.run()
```

## Future Enhancements

- Schema Validation: Integrate Pydantic for payload models.
- Event Batching: Support multiple events in one payload.
- Metrics: Track webhook volume, success rates via Prometheus.
- Testing: Mock middleware for unit tests.

This design ensures webhooks fit naturally into JVspatial's ecosystem while addressing real-world reliability needs.

## Analysis and Recommendations

### Review of Current Design

The proposed webhook architecture was reviewed against three key criteria: (1) simplicity (minimal components, easy to implement/maintain), (2) security (robust auth mechanisms, protection against common vulnerabilities), and (3) flexibility for integration with external systems where payload structure is uncontrolled (requiring URL-embedded route and auth token/key, e.g., as query parameters or path segments, to handle arbitrary payloads without assuming specific formats).

QUICKSTART.md provides general library context (entity-centric design, MongoDB-style queries, FastAPI integration) but no webhook-specific details. The analysis focuses on webhook-architecture.md, cross-referenced with the existing auth subsystem (APIKey entities, middleware, decorators, endpoints).

#### 1. Simplicity (Minimal Components, Easy to Implement/Maintain)
**Status: Confirmed**

- Leverages existing decorator patterns with unified `@webhook_endpoint` that auto-detects functions vs Walker classes, adding only webhook-specific params (e.g., `hmac_secret`, `async_processing`)
- Single `WebhookMiddleware` handles preprocessing (HTTPS, HMAC, idempotency), integrating with existing auth middleware and server registration.
- Metadata-driven (e.g., `_webhook_required=True`) enables deferred, automatic route setup without manual configuration.
- Utilities like `verify_hmac` and `check_idempotency` are lightweight, using GraphContext for storage.
- Maintenance: Changes to middleware propagate to all endpoints; aligns with JVspatial's clean, async philosophy.

No gaps; design is straightforward to implement (decorator usage) and extend.

#### 2. Security (Robust Auth Mechanisms, Protection Against Common Vulnerabilities)
**Status: Confirmed**

- **HTTPS Enforcement:** Middleware rejects non-HTTPS requests, mitigating interception.
- **HMAC Signature Verification:** Per-endpoint secrets validate payload integrity via `X-HMAC-Signature` header, preventing tampering. This complements API key auth: while API keys verify sender identity, HMAC ensures the payload hasn't been altered in transit (layered defense against modification/replays, even if a key is compromised). Standard for webhooks (e.g., Stripe, GitHub); optional but recommended for high-security or uncontrolled payloads.
- **Idempotency Keys:** TTL-based storage (default 24h) in GraphContext avoids duplicate processing/replays; keys from headers or payload.
- **Authentication/Authorization:** Optional integration with existing permissions/roles via `AuthenticationMiddleware`; supports token-based auth, including API keys (hashed secrets, IP restrictions, endpoint permissions).
- **Rate Limiting & Protections:** Ties into existing rate limiters (IP/idempotency/API key-based); payload size caps (1MB); sanitized logging.
- **Error Handling:** Always HTTP 200 on receipt to prevent sender retries on acknowledgments; errors logged/stored for internal retry (exponential backoff, up to 5 attempts).

Addresses key vulnerabilities comprehensively, with HMAC providing essential integrity beyond API key auth.

#### 3. Flexibility for External Integrations (Uncontrolled Payload Structures)
**Status: Gap Identified**

- Current design excels for structured JSON webhooks (e.g., Stripe/GitHub) with fixed paths (e.g., `/webhook/payment`) and parsed payloads (`dict` injection).
- Assumes JSON via `request.body` parsing; lacks support for arbitrary formats (XML, form-data, binary/raw) or URL-embedded auth in path segments, limiting scenarios where external systems use simple URL-based auth for uncontrolled payloads.
- Auth relies on middleware/headers (permissions/roles, API keys via `X-API-Key` or `?api_key=`), but not path-embedded keys, forcing custom handlers per external system and assuming payload format.

This constrains integrations with legacy/variable external services (e.g., IoT devices, custom APIs) that send arbitrary data without JSON or headers.

### Proposed Design Adjustments

To address the flexibility gap while preserving simplicity/security, leverage the existing API key subsystem (APIKey entity, middleware validation) for URL-based auth via path segments—no new entities needed. This reuses hashed key storage, permissions/roles, and validation. Retain HMAC as optional (default enabled) for integrity. Default to raw payloads for handling uncontrolled formats.

1. **URL-Embedded Auth via Path Segments with API Keys:**
   - Update decorators to support templated paths ending with key segment, e.g., `path="/webhook/{route}/{key}"` where {route} is fixed per endpoint (e.g., "stripe"), and {key} is the last path segment (format: key_id:secret).
   - In `WebhookMiddleware`, after HTTPS:
     - Extract route from path (e.g., /webhook/stripe/{key} -> route="stripe"), and {key} as last segment.
     - Validate {key} using existing `_authenticate_api_key` from AuthenticationMiddleware (treat as key_id:secret), which queries APIKey, verifies hash, checks expiration/IP/endpoint permissions (match path to allowed_endpoints), and attaches user to `request.state.current_user`.
     - If valid, proceed to handler for that route; if invalid, 401/403.
   - For multiple routes, use separate decorators with route-specific paths (e.g., @webhook_endpoint("/webhook/stripe/{key}"), @webhook_endpoint("/webhook/iot/{key}"))—explicit, no dynamic dispatch needed.
   - Benefits: Reuses auth; supports per-key permissions/rate limiting; path-based avoids query string pollution.

2. **Default Raw Payload Handling:**
   - Default: Inject `raw_body: bytes = request.body` and `content_type: str = request.headers.get("content-type", "")` into handlers/Walkers for arbitrary formats.
   - Optional: If JSON and no `payload_format=raw` query, also provide parsed `payload: dict`. Handlers access raw for XML/binary (e.g., parse manually), enabling uncontrolled payloads without assumptions.

3. **Integration with Existing Auth and HMAC:**
   - Hybrid: Path key validation first; fall back to header-based (X-API-Key, Bearer) if absent.
   - HMAC: Optional param in decorators (`hmac_secret: Optional[str] = None`); if provided, verify after auth. Defend: Essential for integrity (API key authenticates, HMAC verifies content)—prevents tampering even with valid keys. Disable for low-risk/internal webhooks.
   - Security: API keys already hashed/encrypted; short TTL via `expires_at`; rate-limit per key. Log path keys sanitized.
   - Permissions/Roles: Post-validation, use attached `current_user` for endpoint checks.

4. **Implementation Steps (High-Level):**
   - Extend `WebhookMiddleware`: Parse path for route/{key}; call `AuthenticationMiddleware._authenticate_api_key` on {key}; if hmac_secret, verify signature post-auth. Default inject raw_body/content_type.
   - Update decorators: Support templated paths like "/webhook/{route}/{key}"; add `path_key_auth: bool = True` to enable key extraction. HMAC optional.
   - Utilities: Reuse `APIKey.find_by_key_id`, `verify_secret`; add path parsing for key.
   - Example Usage:
     ```python
     @webhook_endpoint(
         "/webhook/stripe/{key}",
         path_key_auth=True,
         hmac_secret="shared-secret"  # Optional for integrity
     )
     async def stripe_webhook_handler(raw_body: bytes, content_type: str, endpoint):
         # Handle raw payload (e.g., JSON/XML parse as needed), with validated user
         if content_type == "application/json":
             payload = json.loads(raw_body)
         # Process Stripe event
         return endpoint.success(
             message="Stripe webhook processed",
             data={"processed": True}
         )
     ```
     External call: `POST /webhook/stripe/key123:secret123` with raw payload and optional HMAC header.

These adjustments add minimal overhead (path parsing in middleware) while enabling URL-driven flexibility for arbitrary payloads/external systems using existing API keys. HMAC optional for integrity; raw default enhances uncontrolled handling. Simplicity/security preserved by reuse. Test via QUICKSTART.md examples (e.g., webhook with path-embedded key).

Estimated Impact: Low (leverages existing auth); improves webhook usability for uncontrolled integrations.