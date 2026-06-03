# jvspatial Reusable OAuth 2.1 Service — Design (M1)

**Date:** 2026-06-03
**Status:** Approved (design); pending implementation plan
**Repo:** jvspatial (`../jv/jvspatial`, branch `dev`)
**Program:** OAuth-secured MCP for Integral. This is **M1** (foundation). M2 = Integral MCP server endpoint; M3 = Agents-settings UI. Each is its own spec → plan → build cycle.
**Security:** Auth-critical framework feature — implementation MUST run the security-review skill.

## Problem / Goal

jvspatial apps need standards-compliant OAuth 2.1 so external clients (e.g. MCP-aware agents like Claude Code / Cursor) can authenticate against a jvspatial-backed API. jvspatial today has session-JWT auth, refresh tokens, API keys, and RBAC — but **no OAuth 2.1 Authorization Server / Resource Server surface** (no `/authorize`+consent, `/token`, PKCE, DCR, AS/PRM metadata, JWKS, audience-bound access tokens).

Goal: add a **reusable, opt-in OAuth 2.1 AS + RS** to jvspatial, layered on its existing auth (`User`/JWT/`RefreshToken`/RBAC/`Object` storage), so any jvspatial app — Integral first — can secure resources to the MCP-spec **2025-06-18** authorization model.

## Decisions (locked)

1. **Authlib** implements the OAuth 2.1 AS grants + RFC 8414/7591/PKCE + RS token validation. New jvspatial dependency. We own only the storage hooks + jvspatial integration, not the OAuth state machine.
2. **RS256 + JWKS** access tokens (asymmetric; public keys at `/.well-known/jwks.json`). Supports key rotation + separate/multiple resource servers.
3. **DCR (RFC 7591) included** — zero-config client registration for generic MCP clients.
4. **MCP spec target: 2025-06-18** — RS-only-discoverable via PRM; audience-validated; spec permits AS+RS colocation (jvspatial plays both).
5. Built on existing jvspatial auth; **off by default**; existing session-JWT/API-key auth unchanged when disabled.
6. **§3** OAuth bearer accepted app-wide via `accept_oauth_bearer` toggle (audience binding scopes it to the right resource).
7. **§6** Reuse RBAC permission strings as OAuth scopes (configurable supported-scope set).
8. **§7** Framework ships a default consent page; app-overridable via a hook.

## Non-Goals (M1)

- The Integral MCP endpoint (M2) and Agents UI (M3).
- `client_credentials` grant (machine-to-machine) — deferred; M1 ships `authorization_code`+PKCE and `refresh_token`.
- External-IdP delegation (we are the AS).
- Token exchange / on-behalf-of, multi-tenant AS partitioning — future.

## Design

### §1 Placement & wiring
- New subpackage `jvspatial/api/auth/oauth/` (AS provider, RS protector, metadata, consent, key store, storage models, routes).
- Registered by the existing `AuthConfigurator` (mirrors how `/auth/*` routes register via the internal `APIRouter`) when `AuthConfig.oauth_enabled` is true.
- Endpoints under a configurable prefix (default `/oauth`); `.well-known/*` at root.

### §2 Authorization Server (Authlib)
Authlib `AuthorizationServer` bound to Starlette/FastAPI. Grants: **authorization_code (PKCE required)** + **refresh_token**.

| Route | Method | Purpose |
|-------|--------|---------|
| `/oauth/authorize` | GET (+ POST consent) | Validate client/redirect/PKCE/`resource`; require an authenticated jvspatial session (reuse existing login/JWT/session cookie); render consent; on approve issue an `AuthorizationCode`. |
| `/oauth/token` | POST | `authorization_code`+PKCE exchange & `refresh_token` grant → RS256 JWT access token + refresh token. Validates `code_verifier`, redirect match, single-use code, `resource`/audience. |
| `/oauth/register` | POST | DCR (RFC 7591): create `OAuthClient`; return `client_id` (+ `client_secret` for confidential clients; public clients use PKCE only). |
| `/oauth/revoke` | POST | RFC 7009 token revocation (access + refresh). |
| `/.well-known/oauth-authorization-server` | GET | RFC 8414 AS metadata (issuer, endpoints, supported grant types/PKCE methods/scopes, `registration_endpoint`). |
| `/.well-known/jwks.json` | GET | Public signing keys (RS256). |

**Access token claims:** `iss` (issuer_url), `sub` (user id), `aud` (resource canonical URI), `scope`, `client_id`, `exp`/`iat`/`nbf` (UNIX), `jti`. Distinct from jvspatial's existing session JWT (which keeps its current shape).

### §3 Resource Server
- Authlib `ResourceProtector` + a `JWKSTokenVerifier` validating: signature (JWKS), `iss`, `exp`/`nbf`, **`aud` == this resource** (reject mismatched audience — confused-deputy mitigation), and required `scope`.
- **PRM helper:** serve `/.well-known/oauth-protected-resource` (RFC 9728) for a configured resource, listing the AS in `authorization_servers`.
- **401 helper:** `WWW-Authenticate: Bearer resource_metadata="<prm-url>"` on missing/invalid token.
- **Middleware integration:** when `AuthConfig.accept_oauth_bearer` is true, `_authenticate_jwt` (auth_middleware) ALSO accepts OAuth access tokens: if a bearer fails session-JWT validation, try OAuth RS verification (audience-checked); on success set `request.state.user` from `sub` + scopes→permissions. Session JWT path unchanged. (App-wide acceptance; audience binding restricts which tokens pass for a given resource.)

### §4 Storage — new `Object` entities (prime DB; mirror `APIKey`)
- **`OAuthClient`**: `client_id`, `client_secret_hash` (sha256, confidential only), `client_name`, `redirect_uris: List[str]`, `grant_types: List[str]`, `response_types: List[str]`, `scope: str`, `token_endpoint_auth_method` (`none` for public/PKCE), `created_at`, `software_id`/metadata.
- **`AuthorizationCode`**: `code_hash`, `client_id`, `user_id`, `redirect_uri`, `code_challenge`, `code_challenge_method` (`S256`), `scope`, `resource`, `expires_at` (short, ≤10 min), `consumed: bool`.
- **`RefreshToken`** reused; extend with `client_id`, `scope`, `resource` (nullable for legacy session refresh). Rotation reuses existing logic.
- Authlib's grant classes implement `query_*`/`save_*`/`authenticate_*` against these Objects.

### §5 Signing key store
- Generate an RS256 keypair on first boot when `oauth_enabled` and none present; persist as an `Object` (`OAuthSigningKey`: `kid`, `public_pem`, `private_pem` [encrypted-at-rest or env-wrapped], `created_at`, `active`).
- JWKS endpoint serves all `active`+recent public keys (rotation: add new active, keep old for verification window).
- Key source configurable (generated-and-persisted default; allow externally-provided PEM via config/env for ops control).

### §6 Scopes
- OAuth scopes = jvspatial RBAC **permission strings**. `AuthConfig.oauth_supported_scopes` declares the advertised set (app-defined; e.g. a coarse `mcp` scope or resource-specific perms).
- Granted `scope` on a token = requested ∩ user's effective permissions (`get_effective_permissions`). RS enforces required scope per resource/endpoint.

### §7 Consent
- jvspatial ships a **default consent endpoint/page**: `GET /oauth/authorize` (session-authenticated) renders minimal HTML listing client name + requested scopes; POST approves/denies.
- **App-overridable:** `AuthConfig.oauth_consent_handler` (callable/template hook) lets an app (Integral) supply its own themed consent UI; default used when unset.
- Requires an active jvspatial session — the authorize step identifies the user via existing login (browser session/JWT); unauthenticated → redirect to the app's login then back.

### §8 Config (`AuthConfig` additions — all off/empty by default)
`oauth_enabled: bool=False`, `oauth_issuer_url: str`, `oauth_prefix: str="/oauth"`, `oauth_supported_scopes: List[str]=[]`, `oauth_dcr_enabled: bool=True`, `oauth_access_token_ttl_minutes: int=60`, `oauth_code_ttl_seconds: int=300`, `accept_oauth_bearer: bool=False`, `oauth_signing_key_source` (`generate`|`env`), `oauth_consent_handler: Optional[...]`. Env-backed where secret-bearing.

### §9 Security posture
- PKCE `S256` required; reject plain. Single-use auth codes; short TTL; redirect-URI exact match. Refresh rotation on. Audience validation mandatory; **no token passthrough** to upstream APIs. HTTPS assumed (issuer/redirects). Confidential client secrets sha256-hashed; public clients PKCE-only. DCR rate-limited (reuse jvspatial rate-limit middleware).
- Implementation MUST run security-review.

## File structure (target)
```
jvspatial/api/auth/oauth/
  __init__.py
  server.py          # Authlib AuthorizationServer setup + grant registration
  grants.py          # AuthorizationCodeGrant(+PKCE), RefreshTokenGrant bound to Objects
  resource.py        # ResourceProtector + JWKSTokenVerifier + PRM/401 helpers
  metadata.py        # RFC 8414 AS metadata + JWKS builders
  consent.py         # default consent page + override hook
  keys.py            # RS256 key store (generate/persist/rotate/JWKS)
  models.py          # OAuthClient, AuthorizationCode, OAuthSigningKey (+ RefreshToken ext)
  routes.py          # APIRouter: /authorize /token /register /revoke + .well-known
jvspatial/api/config_groups.py   # AuthConfig OAuth fields (modify)
jvspatial/api/components/auth_configurator.py  # register oauth routes when enabled (modify)
jvspatial/api/components/auth_middleware.py    # accept_oauth_bearer path (modify)
pyproject.toml                   # add authlib (modify)
```

## Testing
- **Metadata:** AS metadata + JWKS shape; PRM shape; disabled → 404/absent.
- **DCR:** register public + confidential client; reject bad redirect_uris.
- **authorize→token:** full PKCE happy path (S256); **tampered `code_verifier` rejected**; reused code rejected; redirect mismatch rejected; `resource`/audience recorded.
- **refresh:** rotation issues new, invalidates old; revoked refresh rejected.
- **revoke:** access + refresh revocation honored.
- **RS:** valid token accepted (correct aud/scope); rejected for wrong-aud / expired / bad-sig / missing-scope; 401 carries `WWW-Authenticate` + `resource_metadata`.
- **middleware:** with `accept_oauth_bearer`, `@endpoint(auth=True)` accepts an OAuth token and resolves `request.state.user`; session-JWT path unchanged.
- **disabled invariant:** `oauth_enabled=False` → no oauth routes, no `.well-known`, existing auth suite fully green.

## Assumptions to verify during planning
- Authlib's Starlette integration composes with jvspatial's `APIRouter`-based registration + middleware order (verify it sits inside the host pipeline, not a bypass).
- `Object` storage + `GraphContext.save/find` supports the query patterns Authlib's grant hooks need (lookup by client_id, code_hash).
- jvspatial's session identity is reachable from `/oauth/authorize` to identify the consenting user.
- Key-at-rest encryption approach for `OAuthSigningKey.private_pem` (env-wrapped vs KMS) — decide in plan.

## Out of scope (later milestones)
- **M2:** Integral MCP server endpoint (jvspatial `@endpoint`s driving the `mcp` SDK `StreamableHTTPSessionManager.handle_request`, secured by this RS, tools from `mcp_adapter`, in-process dispatch).
- **M3:** Agents-settings UI surfacing the endpoint + connect flow.

---

# M1b Design Addendum — Authlib AS integration (decisions + wiring map)

**Date:** 2026-06-03. Captures M1b architecture decisions + the Authlib/jvspatial integration facts researched before planning. M1a (foundation) is built on `feat/oauth2-service`.

## Locked M1b decisions
- **Library:** Authlib 1.x framework-agnostic `authlib.oauth2.rfc6749.AuthorizationServer` (no Flask/Django integration; we write the Starlette binding).
- **Async/sync bridge:** Authlib core is **synchronous**; jvspatial DB is **async-only** (no sync path; asyncpg has no sync API). Bridge = **anyio thread-bridge**: route handlers run Authlib via `await anyio.to_thread.run_sync(server.create_*_response, oauth_req)`; inside Authlib's sync grant hooks, reach M1a async storage via `anyio.from_thread.run(async_fn, *args)` (valid because the worker was started by `to_thread.run_sync`, which installs the blocking portal). The process-default `GraphContext` is a boot-time singleton, reachable on the host loop where `from_thread.run` executes.
- **Access tokens:** RFC 9068 `authlib.oauth2.rfc9068.JWTBearerTokenGenerator` (subclass; `get_jwks()` returns the M1a active **private** JWK with `kid`+`alg=RS256`; `authlib.jose.jwt.encode` auto-stamps `kid` into the `at+jwt` header). `get_audiences()` returns the resource indicator. Registered via `server.register_token_generator("default", gen)`.
- **PKCE:** `server.register_grant(AuthCodeGrant, [authlib.oauth2.rfc7636.CodeChallenge(required=True)])` — mandatory S256.
- **Grants/endpoints:** `AuthorizationCodeGrant` (save/query/delete code + authenticate_user, hooks bridge to `AuthorizationCode` Object), `RefreshTokenGrant` (`INCLUDE_NEW_REFRESH_TOKEN=True` rotation, reuse `RefreshToken` Object), `rfc7591.ClientRegistrationEndpoint` (DCR → `OAuthClient`), `rfc7009.RevocationEndpoint`. AS metadata (RFC 8414) is **hand-served** JSON (Authlib only validates via `rfc8414.AuthorizationServerMetadata`).
- **Client adapter:** a wrapper over `OAuthClient` satisfying `ClientMixin` (`get_client_id`, `get_default_redirect_uri`, `check_redirect_uri` exact-match, `check_client_secret` via M1a `verify_client_secret`, `check_endpoint_auth_method("none","token")` true for public/PKCE, `check_response_type`, `check_grant_type`, `get_allowed_scope`).
- **Version traps:** don't pass `OAuth2Request(body=...)` (deprecated 1.6.x) and don't read `request.data`/`.client_id` (deprecated → `request.payload.*`); bind by subclassing `OAuth2Request` and overriding `args`/`form` to return dicts.

## jvspatial wiring map (file:line)
- **Route registration:** `AuthConfigurator` creates `APIRouter(prefix="/auth", tags=["Auth"])` (`auth_configurator.py:136`); mounted `app.include_router(router, prefix=APIRoutes.PREFIX)` (`server_app_factory.py:70`, `APIRoutes.PREFIX` default `/api`). Add a parallel `oauth_router` gated on `oauth_enabled`, mounted the same way. **Wrinkle:** `.well-known/oauth-authorization-server`, `.well-known/jwks.json`, and PRM must sit at **root**, not under `/api` — mount those on the app without the `/api` prefix (or set `issuer_url` to include `/api` and serve metadata at `{issuer}/.well-known/...` per RFC 8414 path-insertion). Resolve in M1b-3.
- **AuthConfig at runtime:** `Server._configure_authentication()` (`server.py:241-266`) stores `self._auth_config`; route handlers read it via the server instance or a `get_oauth_config()` dependency mirroring `get_auth_service()` (`auth_configurator.py:131`).
- **Session user for `/authorize`:** `get_current_user` dependency (`auth_configurator.py:145-161`) returns `UserResponse(id,email,name,roles,permissions,...)` but reads a **bearer** (`HTTPAuthorizationCredentials`), not a cookie. **Wrinkle:** browser OAuth authorize flows usually carry a session cookie. M1b must decide how the consent step identifies the user — options: (a) integral frontend drives `/authorize` with the user's bearer; (b) add a session-cookie auth path for the authorize GET. Resolve in M1b-2 (consent), coordinate with M2/M3.
- **Startup hook:** `server.lifecycle_manager.add_startup_hook(func)` (`lifecycle.py:50-72`, async-aware) — register `ensure_signing_key()` when `oauth_enabled`, mirroring the admin-bootstrap pattern (`server.py:203-239`).
- **HTML/redirect:** plain `starlette.responses.HTMLResponse`/`RedirectResponse`; no template dir (consent page = inline HTML or a module string).
- **anyio:** available via Starlette; `anyio.to_thread.run_sync` + `anyio.from_thread.run` confirmed.

## M1b phasing (each its own plan + subagent-driven build)
- **M1b-1 — Core AS + bridge:** Starlette `OAuth2Request` wrapper + `AuthorizationServer` subclass (3 binding methods + `query_client`/`save_token`), anyio thread-bridge helper, `ClientMixin` adapter over `OAuthClient`, `AuthorizationCodeGrant` + PKCE bridged to `AuthorizationCode`, RFC 9068 RS256 token generator wired to `keys.py`, `/oauth/token` + `/oauth/authorize` (consent-approve POST issuing a code; GET consent stub). Tests: PKCE authcode→token happy path + tampered-verifier reject (drive the server in-process with a fake authenticated user).
- **M1b-2 — Refresh + consent + session:** `RefreshTokenGrant` (rotation), consent page + the session-user resolution decision, scope = requested ∩ user permissions.
- **M1b-3 — DCR + revocation + metadata routes:** `ClientRegistrationEndpoint`, `RevocationEndpoint`, hand-served RFC 8414 metadata + `/.well-known/jwks.json` (root-mounted), `oauth_router` registration + startup key hook.

## M1a carry-ins for M1b
- Add `AuthConfig.oauth_signing_key_source` (`generate|env`) before wiring `ensure_signing_key()` into boot.
- `keys._jwks_keys()` needs a rotation/time-window filter when rotation lands.
- `OAuthClient` gains DCR metadata fields (`software_id`, etc.) in M1b-3.
