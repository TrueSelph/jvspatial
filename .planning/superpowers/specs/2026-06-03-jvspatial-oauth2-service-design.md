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
