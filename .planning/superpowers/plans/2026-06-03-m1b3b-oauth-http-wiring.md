# M1b-3b — OAuth HTTP wiring (routes + mount + consent/session + startup + rate-limit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps. **Security-critical** (auth, network-exposed) — gets a security review. This phase is INTEGRATION-heavy: validate by booting a real `Server` and making HTTP requests (less unit-isolated than M1b-1..3a).

**Goal:** Expose the (already-built, tested) OAuth AS over HTTP in jvspatial: mount `/oauth/{authorize,token,register,revoke}` + root `/.well-known/{oauth-authorization-server,jwks.json}`, wire through `AuthConfigurator` gated on `oauth_enabled`, resolve the session user (+ effective permissions) for `/authorize`, run `ensure_signing_key` at startup, and rate-limit `/register` (review I-1).

**Architecture:** A single `build_authorization_server(issuer, resource)` instance (M1b-1..3a) is built once when `oauth_enabled`, stored on the configurator, and shared by route handlers. Handlers convert the Starlette `Request` → `StarletteOAuth2Request` (via `build_oauth2_request`) and call the server's `async_*` methods, returning the `OAuthHttpResponse` as a Starlette response. `/authorize` requires a bearer (jvspatial `get_current_user`); the integral frontend drives it. Metadata/JWKS are plain JSON routes at root.

**Tech Stack:** jvspatial `Server`/`AuthConfigurator`/`server_app_factory`/`lifecycle`/rate-limit, FastAPI `APIRouter`, the M1b oauth subpackage, `TestClient`/`JVSpatialTestClient`. venv `.venv`. Pre-commit: black/isort/flake8(D-codes)/mypy/detect-secrets.

**Repo/branch:** jvspatial `feat/oauth2-service` (HEAD after M1b-3a `9618ca2`).

> **RUNTIME-VALIDATION:** This phase's truth is a booting Server. Each task's integration test boots `Server(...oauth_enabled=True...)` and hits HTTP; adapt wiring to what actually mounts/runs. Verify `server.get_app()`, `app.include_router(router, prefix="")` root mount, and that `AuthConfigurator`/`server_app_factory` expose+mount the new routers. If `get_current_user` / config access differ at runtime, adapt and report.

---

## Key integration facts (confirmed)
- `app = server.get_app()` (`server_app_factory.py:92`); `Server(title=, db_type="json", db_path=, auth_enabled=True, jwt_secret=, jwt_algorithm="HS256", ...)`. OAuth fields go through `AuthConfig` (already added).
- Test harness: `from jvspatial.testing import JVSpatialTestClient` → `JVSpatialTestClient(server)` wraps `TestClient(server.app)`; or `from fastapi.testclient import TestClient; TestClient(server.get_app())`.
- Mount: `server_app_factory._create_app*` does `app.include_router(self._auth_router, prefix=APIRoutes.PREFIX)` (~line 70). Add `app.include_router(self._oauth_router, prefix=APIRoutes.PREFIX)` + `app.include_router(self._well_known_router, prefix="")` (root) when present. No global prefix.
- `AuthConfigurator._register_auth_endpoints()` builds `auth_router`; add oauth/well-known router build (gated on `oauth_enabled`) + expose as `.oauth_router`/`.well_known_router` properties.
- Startup: `server.lifecycle_manager.add_startup_hook(async_fn)`; accessible at configure time.
- `get_current_user` (auth_configurator ~145) is **bearer-only** → `UserResponse(id, roles, permissions, ...)`. `get_effective_permissions(roles, permissions, role_permission_mapping)` in `rbac.py`.
- Rate-limit: `server.config.rate_limit.rate_limit_overrides["/api/oauth/register"] = {"requests": N, "window": S}` + RateLimitMiddleware (enabled via config).

---

## Task 1: OAuth routers + mount + startup hook (metadata/JWKS reachable over HTTP)

**Files:** create `jvspatial/api/auth/oauth/routes.py`; modify `jvspatial/api/components/auth_configurator.py` + `jvspatial/api/server_app_factory.py` + `jvspatial/api/server.py` (startup hook); test `tests/api/auth/oauth/test_oauth_http_wellknown.py`.

- [ ] **Step 1: failing integration test** — boot a Server with oauth enabled, GET the two well-known docs over HTTP:
```python
"""OAuth HTTP wiring: /.well-known metadata + jwks served at root when enabled."""

import tempfile, uuid
import pytest
from fastapi.testclient import TestClient
from jvspatial.api.server import Server


def _server(tmpdir):
    return Server(
        title="oauth-test", db_type="json", db_path=f"{tmpdir}/db_{uuid.uuid4().hex}",
        auth_enabled=True, jwt_secret="x" * 40, jwt_algorithm="HS256",
        oauth_enabled=True, oauth_issuer_url="https://as.example",
        oauth_supported_scopes=["mcp"],
    )


def test_wellknown_metadata_and_jwks_served():
    with tempfile.TemporaryDirectory() as tmp:
        app = _server(tmp).get_app()
        client = TestClient(app)
        md = client.get("/.well-known/oauth-authorization-server")
        assert md.status_code == 200
        body = md.json()
        assert body["issuer"] == "https://as.example"
        assert body["token_endpoint"].endswith("/oauth/token")
        assert "S256" in body["code_challenge_methods_supported"]

        jwks = client.get("/.well-known/jwks.json")
        assert jwks.status_code == 200
        keys = jwks.json()["keys"]
        assert len(keys) >= 1 and keys[0]["kty"] == "RSA" and "d" not in keys[0]


def test_oauth_disabled_no_wellknown():
    with tempfile.TemporaryDirectory() as tmp:
        s = Server(title="t", db_type="json", db_path=f"{tmp}/db_{uuid.uuid4().hex}",
                   auth_enabled=True, jwt_secret="x" * 40)  # oauth_enabled defaults False
        client = TestClient(s.get_app())
        assert client.get("/.well-known/jwks.json").status_code == 404
```
(If `Server(**kwargs)` doesn't accept `oauth_*` kwargs directly, construct via whatever config path AuthConfig uses — e.g. an `auth=AuthConfig(...)` object or env; verify the real Server signature and adapt the fixture, keeping the HTTP assertions.)

- [ ] **Step 2: run, verify FAIL** (404 — routes not mounted; or Server rejects oauth kwargs).

- [ ] **Step 3: implement.**
  1. `jvspatial/api/auth/oauth/routes.py` — `build_oauth_routers(auth_config, get_current_user) -> tuple[APIRouter, APIRouter]`:
     - Build the server once: `server = build_authorization_server(issuer=auth_config.oauth_issuer_url, resource=auth_config.oauth_issuer_url)` (resource defaulting to issuer for now; per-request RFC-8707 resource is a noted future item). Store it (closure).
     - `well_known_router = APIRouter(tags=["OAuth"])`:
       - `GET /.well-known/oauth-authorization-server` → `from jvspatial.api.auth.oauth.metadata import build_as_metadata; return build_as_metadata(issuer=auth_config.oauth_issuer_url, prefix=auth_config.oauth_prefix, scopes_supported=auth_config.oauth_supported_scopes)`.
       - `GET /.well-known/jwks.json` → `from jvspatial.api.auth.oauth import keys; return await keys.build_jwks()`.
     - `oauth_router = APIRouter(prefix=auth_config.oauth_prefix, tags=["OAuth"])`:
       - `POST /token` → `req = await build_oauth2_request(request); resp = await server.async_create_token_response(req); return _to_response(resp)`.
       - `POST /register` → `body = await request.json(); resp = await server.async_register_client(await build_oauth2_request(request), body); return _to_response(resp)`.
       - `POST /revoke` → `resp = await server.async_revoke_token(await build_oauth2_request(request)); return _to_response(resp)`.
       - `/authorize` GET+POST → **stubbed in Task 1** (Task 3 adds consent/session): for now `GET` returns a minimal HTML "consent" page and `POST` (with `?approve=1` or form) resolves the user + issues a code. To keep Task 1 scoped to mounting, implement `/authorize` minimally or defer its body to Task 3 — but DO register the routes so the metadata endpoints are the Task-1 focus. (Acceptable: Task 1 wires token/register/revoke/well-known + a placeholder authorize; Task 3 completes authorize consent/session.)
     - `_to_response(holder)`: convert `OAuthHttpResponse` → `starlette.responses.JSONResponse(holder.body_json, status_code=holder.status_code)` for JSON, or `Response`/`RedirectResponse` when it carries a `location` header (302/303). Reuse the holder's headers.
  2. `auth_configurator.py`: in `_register_auth_endpoints()` (gated on `getattr(self._auth_config, "oauth_enabled", False)`), call `self._oauth_router, self._well_known_router = build_oauth_routers(self._auth_config, get_current_user)`; add `oauth_router`/`well_known_router` properties; register the startup hook: `if self._server: self._server.lifecycle_manager.add_startup_hook(_ensure_oauth_key)` where `_ensure_oauth_key` is `async def: from jvspatial.api.auth.oauth import keys; await keys.ensure_signing_key()`.
  3. `server_app_factory.py`: after the auth_router mount (~line 70), add:
     ```python
     if getattr(self, "_oauth_router", None) is not None:
         app.include_router(self._oauth_router, prefix=APIRoutes.PREFIX)
     if getattr(self, "_well_known_router", None) is not None:
         app.include_router(self._well_known_router, prefix="")
     ```
     and ensure the factory copies `oauth_router`/`well_known_router` off the configurator like it does `_auth_router` (mirror `server.py:_configure_authentication` storing `self._auth_router = auth_configurator.auth_router`; add `self._oauth_router`/`self._well_known_router`).
  4. Confirm `Server` accepts the oauth config (via `AuthConfig`); if Server's `__init__` doesn't pass `oauth_*` kwargs into AuthConfig, thread them (or accept an `auth=AuthConfig(...)`); adapt the test fixture to the real path.
  RUNTIME-VALIDATION: this is multi-file framework wiring — boot the test and iterate until the well-known docs return 200 and oauth-disabled returns 404. Report exactly what you wired in each file.

- [ ] **Step 4: PASS** (metadata + jwks 200; disabled → 404). Existing suite green (`tests/api/auth`).
- [ ] **Step 5: lint/type; commit** the touched files + test → `feat(oauth): mount OAuth routers + well-known metadata/jwks + startup key hook`.

---

## Task 2: End-to-end HTTP flow (DCR → token → refresh → revoke) integration test + fixes

**Files:** test `tests/api/auth/oauth/test_oauth_http_flow.py`; fix `routes.py`/wiring as the test reveals.

- [ ] **Step 1: failing test** — boot the Server, then over HTTP: register a public client (DCR), then exercise `/token` is reachable and errors cleanly without a code (full authorize needs Task 3). Minimal end-to-end that doesn't need consent:
```python
"""OAuth HTTP: DCR over HTTP persists a client and returns client_id."""
import tempfile, uuid
from fastapi.testclient import TestClient
from jvspatial.api.server import Server


def test_dcr_over_http():
    with tempfile.TemporaryDirectory() as tmp:
        s = Server(title="t", db_type="json", db_path=f"{tmp}/db_{uuid.uuid4().hex}",
                   auth_enabled=True, jwt_secret="x" * 40, oauth_enabled=True,
                   oauth_issuer_url="https://as.example", oauth_supported_scopes=["mcp"])
        client = TestClient(s.get_app())
        r = client.post("/api/oauth/register", json={
            "client_name": "Claude", "redirect_uris": ["https://c.example/cb"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"], "token_endpoint_auth_method": "none", "scope": "mcp"})
        assert r.status_code in (200, 201), r.text
        assert r.json()["client_id"]
        # https-only redirect guard still applies over HTTP:
        bad = client.post("/api/oauth/register", json={
            "client_name": "x", "redirect_uris": ["http://evil.example/cb"],
            "grant_types": ["authorization_code"], "response_types": ["code"],
            "token_endpoint_auth_method": "none"})
        assert bad.status_code >= 400
```
- [ ] **Step 2-4:** run; fix the DCR HTTP path (JSON body read, `async_register_client` over the real Request) until green; existing suite green.
- [ ] **Step 5: commit** → `test(oauth): end-to-end DCR over HTTP`.

---

## Task 3: `/authorize` consent + session-user resolution (trust boundary)

**Files:** modify `routes.py` (+ optional `oauth/consent.py`); test `tests/api/auth/oauth/test_oauth_authorize_http.py`.

- [ ] **Step 1: failing test** — a logged-in user (bearer) drives authorize → consent → approve → redirect with `?code=`; then `/token` exchanges it. (Create a user via the auth service / a test fixture to get a bearer; or stub `get_current_user`.) Assert: unauthenticated `/authorize` → 401; authenticated approve → 302 with code; token exchange with PKCE → access token whose `scope` is the user's effective permissions ∩ request.
- [ ] **Step 2-4:** implement:
  - `GET /oauth/authorize` (Depends `get_current_user`): validate the request via `server.get_consent_grant` (or build the consent data) and render an HTML consent page (client name + requested scopes + approve/deny form carrying the original params). `oauth_consent_handler` config hook overrides the default page when set.
  - `POST /oauth/authorize` (Depends `get_current_user`): on approve, build `grant_user = {"id": user.id, "permissions": list(get_effective_permissions(user.roles, user.permissions, auth_config.role_permission_mapping))}` — **THIS is the trust boundary: permissions come from the authenticated session user, never from client input** — then `resp = await server.async_create_authorization_response(req, grant_user=grant_user)`; return the redirect. On deny, redirect with `error=access_denied`.
  - Verify scope∩permissions end-to-end (a user lacking `admin` can't get it even if the client+request ask).
- [ ] **Step 5: commit** → `feat(oauth): /authorize consent + session-user permission resolution`.

---

## Task 4: DCR rate-limit (review I-1)

**Files:** modify the configurator/server config to add a rate-limit override for `/api/oauth/register`; test.

- [ ] **Step 1: failing test** — boot with oauth enabled; POST `/api/oauth/register` more than the cap within the window → eventually 429.
- [ ] **Step 2-4:** when `oauth_enabled`, set `server.config.rate_limit.rate_limit_overrides["{PREFIX}/oauth/register"] = {"requests": <cap>, "window": <s>}` (cap e.g. 10/min) and ensure rate-limit middleware is enabled. Add an `oauth_dcr_rate_limit` AuthConfig knob (default e.g. 10) if clean. Verify a burst trips 429 while a normal single registration succeeds.
- [ ] **Step 5: commit** → `fix(oauth): rate-limit dynamic client registration (open-DCR abuse, I-1)`.

---

## Task 5: M1b-3b verification + security review
- [ ] full oauth suite + a Server-boot integration slice green; existing `tests/api/auth` green.
- [ ] security review: route exposure (no internal leak), consent CSRF (the approve POST — does it need a CSRF token / does bearer-auth suffice?), `/authorize` open-redirect (redirect_uri validated by Authlib exact-match — confirm), rate-limit effectiveness, that `grant_user.permissions` cannot be influenced by client input.

## Self-Review Notes
- Covers addendum M1b-3 wiring + review I-1. Per-request RFC-8707 `resource`→`aud` (token audience varies per resource) remains a noted future item (M1c/M2 may need it for the MCP resource). Access-token `jti` denylist still future.
- **Trust boundary (Task 3):** `/authorize` POST derives `grant_user.permissions` ONLY from the authenticated session user via `get_effective_permissions` — never from request params. This is the load-bearing invariant the M1b-2 review flagged.
- Names: `build_oauth_routers`, `_to_response`, `_ensure_oauth_key`, `oauth_router`/`well_known_router` consistent.

## Next: M1c (Resource Server: JWKS verifier + PRM + 401 + accept_oauth_bearer middleware) → M2 (Integral MCP endpoint) → M3 (Agents UI).
