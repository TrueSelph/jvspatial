# OAuth-secured MCP for Integral — Resume Handoff

**As of:** 2026-06-03. **Branch:** jvspatial `feat/oauth2-service` (NOT merged to `dev`).
**Status:** OAuth 2.1 Authorization Server fully built + security-reviewed + HTTP-mounted. `tests/api` 569 passed; oauth suite 34 passed; full jvspatial suite green.

## Program shape (OAuth-secured MCP)
jvspatial gains a reusable OAuth 2.1 AS+RS; Integral uses it to secure an MCP server endpoint; the Agents settings UI surfaces it. External agents (Claude Code/Cursor) connect via MCP (BYOA reduced to MCP-only). One resident harness = the embedded jvagent cockpit.

Milestones: **M1** jvspatial OAuth service → **M2** Integral MCP endpoint → **M3** Agents UI.
M1 sub-phases: M1a (foundation) ✅ · M1b-1 (AS core) ✅ · M1b-2 (refresh+scope) ✅ · M1b-3a (DCR+revocation+metadata+reuse-detection) ✅ · **M1b-3b (HTTP wiring) — Task 1 done, Tasks 2-5 remain** · M1c (Resource Server) — not started.

## Done (committed on feat/oauth2-service, all security-reviewed)
- **M1a** `oauth/models.py` (OAuthClient/AuthorizationCode/OAuthSigningKey + OAuthRefreshToken), `oauth/keys.py` (RS256 keystore+JWKS), AuthConfig oauth fields, cryptography dep.
- **M1b-1** `oauth/{bridge,requests,client_adapter,server}.py` — Authlib AS, authcode+**mandatory-S256 PKCE**, RS256 RFC-9068 tokens, anyio sync/async bridge. (Critical PKCE-bypass fixed.)
- **M1b-2** refresh issuance+**rotation/revocation** (`oauth/refresh_store.py`), **scope∩permissions**, nbf, atomic single-use. (I-1 lockout + I-2 atomicity fixed.)
- **M1b-3a** `oauth/{dcr,revocation,metadata}.py` — DCR (RFC 7591, **https-only redirects**), revocation (RFC 7009), **refresh reuse-detection (family revocation)**, RFC 8414 metadata builder.
- **M1b-3b Task 1** `oauth/routes.py` + wiring in `auth_configurator.py`/`server.py`/`server_app_factory.py` — `/.well-known/{oauth-authorization-server,jwks.json}` at root, `/api/oauth/{token,register,revoke}` mounted, `/oauth/authorize` placeholder, startup `ensure_signing_key`, auth-exempt public paths. Config path: `Server(auth=dict(auth_enabled=True, jwt_secret=..., oauth_enabled=True, oauth_issuer_url=..., oauth_supported_scopes=[...]))`.

## NEXT — resume M1b-3b (plan: `.planning/superpowers/plans/2026-06-03-m1b3b-oauth-http-wiring.md`, task #25)
1. **KNOWN BUG (fix first):** `build_as_metadata` (`oauth/metadata.py`) advertises `{issuer}/oauth/token` etc., but routes mount under `APIRoutes.PREFIX` at `/api/oauth/token`. Pass an `api_prefix` into `build_as_metadata` and the well-known route so token/authorize/register/revoke URLs include `/api`; `jwks_uri` + the metadata doc itself stay at root. Without this, a client following metadata 404s.
2. **Task 2** — end-to-end DCR-over-HTTP test (+ the fix above).
3. **Task 3** — `/authorize` consent page + session-user resolution. **TRUST BOUNDARY:** the approve POST builds `grant_user={"id": user.id, "permissions": list(get_effective_permissions(user.roles, user.permissions, auth_config.role_permission_mapping))}` — permissions come ONLY from the authenticated session user (`get_current_user`, bearer), NEVER client input. `get_effective_permissions` in `api/auth/rbac.py`.
4. **Task 4** — DCR rate-limit (review I-1) — **public-launch blocker**. `server.config.rate_limit.rate_limit_overrides["/api/oauth/register"] = {"requests": N, "window": S}`.
5. **Task 5** — verification + security review.

## Then
- **M1c** — Resource Server: `authlib.oauth2.rfc9068.JWTBearerTokenValidator(issuer, resource_server)` + `ResourceProtector` (JWKS verify, aud-bound), serve RFC 9728 PRM (`/.well-known/oauth-protected-resource`), 401 `WWW-Authenticate: …resource_metadata=…`, and `accept_oauth_bearer` middleware path in `auth_middleware` (accept OAuth access tokens on `@endpoint(auth=True)` alongside session JWTs).
- **M2** — Integral MCP server endpoint (separate repo `/Users/eldonmarks/Briefcase/dev/integral`): jvspatial `@endpoint`s driving `mcp` SDK `StreamableHTTPSessionManager.handle_request`, secured by M1c RS, tools from `mcp_adapter` catalogue, in-process dispatch (reuse `IntegralEmbeddedAction._call_endpoint` pattern). Spec/addendum: integral `.planning/`.
- **M3** — Agents-settings MCP UI (integral frontend `AgentsSection.tsx`).

## Key constraints (don't relitigate)
- Authlib core is SYNC; jvspatial DB is ASYNC-only → anyio thread-bridge (`oauth/bridge.py`: `run_sync_with_async_bridge`/`call_async`). Don't bypass jvspatial plumbing (routes go through `@endpoint`/AuthConfigurator/middleware, not a raw ASGI mount).
- Authlib 1.7.2: use `request.payload` (not deprecated `request.data`); `OAuth2Request` args/form overridden in `oauth/requests.py`.
- Pre-commit enforces black/isort/flake8(D-codes)/mypy/detect-secrets.
- jvspatial `.planning/` IS git-tracked (commit docs there).

## Deferred / future (tracked, not bugs)
- Per-request RFC-8707 `resource`→`aud` (token audience fixed at build time today).
- Access-token `jti` denylist (stateless JWTs can't be revoked; refresh revocation works).
- Multi-worker atomicity: single-use/rotation serialized by single-process anyio bridge; needs a DB conditional-update (CAS) primitive before horizontal scaling (review I-2).
