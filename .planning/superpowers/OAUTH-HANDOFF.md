# OAuth-secured MCP for Integral — Resume Handoff

**As of:** 2026-06-03. **Branch:** jvspatial `feat/oauth2-service` (HEAD `f06dcbe`, NOT merged to `dev`).
**Status:** **M1 COMPLETE** — reusable jvspatial OAuth 2.1 Authorization Server **+ Resource Server**, fully built, security-reviewed, HTTP-mounted, off by default. oauth suite **55 passed**; full `tests/api` green.

## Program (OAuth-secured MCP)
jvspatial gains a reusable OAuth 2.1 AS+RS; Integral uses it to secure an MCP server endpoint; the Agents settings UI surfaces it. External agents connect via MCP (BYOA = MCP-only). One resident harness = embedded jvagent cockpit.
**M1** jvspatial OAuth service ✅ → **M2** Integral MCP endpoint (not started) → **M3** Agents UI (not started).

## M1 — DONE (all on feat/oauth2-service, every phase TDD + spec + security review)
- **M1a** foundation: `oauth/models.py` (OAuthClient/AuthorizationCode/OAuthSigningKey/OAuthRefreshToken), `oauth/keys.py` (RS256 keystore+JWKS), AuthConfig oauth fields, cryptography dep.
- **M1b-1** AS core: Authlib server, authcode + **mandatory-S256 PKCE** → RS256 RFC-9068 tokens, anyio sync/async bridge. (Critical PKCE-bypass fixed.)
- **M1b-2** refresh issuance + **rotation/revocation** + **reuse-detection (family)** + **scope∩permissions** + nbf + atomic single-use. (I-1 lockout, I-2 atomicity fixed.)
- **M1b-3a** `oauth/{dcr,revocation,metadata}.py` — DCR (RFC 7591, **https-only redirects**), revocation (RFC 7009), RFC 8414 metadata builder.
- **M1b-3b** `oauth/routes.py` + wiring — `/.well-known/{oauth-authorization-server,jwks.json}` at root, `/api/oauth/{authorize,token,register,revoke}` mounted, **consent + session-user permission resolution** (trust boundary), startup key hook, **DCR rate-limit** (I-1), metadata api-prefix fix, **deny-path open-redirect fixed**.
- **M1c** `oauth/resource.py` + middleware — RS256 access-token **verifier** (audience-bound, JWKS), **PRM** (RFC 9728) + **`WWW-Authenticate` 401 discovery**, **`accept_oauth_bearer`** middleware (OAuth tokens authorize `@endpoint(auth=True)` alongside session JWTs). Security-reviewed: audience binding, alg/key-confusion, synthesized-principal all verified secure (fails closed on role-gated endpoints).

Enable per app: `Server(auth=dict(auth_enabled=True, jwt_secret=..., oauth_enabled=True, oauth_issuer_url="https://host", oauth_supported_scopes=[...], accept_oauth_bearer=True))`.

## NEXT
1. **Merge M1** — `feat/oauth2-service` → jvspatial `dev` (self-contained, off-by-default, full suite green). Review + FF/merge when ready.
2. **M2 — Integral MCP server endpoint** (repo `/Users/eldonmarks/Briefcase/dev/integral`). Plan: jvspatial `@endpoint`s driving `mcp` SDK `StreamableHTTPSessionManager.handle_request`, secured by M1c RS (`accept_oauth_bearer` + the verifier; serve PRM for the MCP resource), tools from `mcp_adapter` catalogue, in-process dispatch reusing `IntegralEmbeddedAction._call_endpoint`. Integral configures jvspatial oauth (`oauth_enabled`, `oauth_issuer_url`, `accept_oauth_bearer`). Spec/addendum in integral `.planning/`. Brainstorm → spec → plan → build.
3. **M3 — Agents-settings MCP UI** (integral frontend `frontend/src/features/settings/sections/AgentsSection.tsx`): surface the MCP endpoint + connect instructions (with DCR, clients self-register → thin UI). Task #16.

## OAuth backlog (deferred, tracked — not blockers)
- Per-request RFC-8707 `resource`→`aud` (today aud = issuer; single-process AS+RS). Needed if MCP resource URI ≠ issuer.
- Access-token `jti` denylist (stateless JWT; refresh revocation works; bound by exp).
- Multi-worker atomicity: single-use/rotation serialized by single-process anyio bridge; needs a DB conditional-update (CAS) primitive before horizontal scaling (review I-2).
- DCR rate-limit identifier is per-(IP+User-Agent) + no XFF (shared rate_limit middleware); tighten to IP-only + proxy XFF for the register override.
- Decide whether literal `scope=*` is grantable via OAuth (maps to permission-wildcard; never passes role gates).

## Key constraints (don't relitigate)
- Authlib core SYNC, jvspatial DB ASYNC-only → anyio thread-bridge (`oauth/bridge.py`). No jvspatial-plumbing bypass (routes via AuthConfigurator/middleware, not raw ASGI mount).
- Authlib 1.7.2: `request.payload` (not deprecated `request.data`); `OAuth2Request.args/form` overridden in `oauth/requests.py`.
- Pre-commit: black/isort/flake8(D-codes)/mypy/detect-secrets. jvspatial `.planning/` IS git-tracked.
- Tests over HTTP need `AUTHLIB_INSECURE_TRANSPORT=1` (TestClient is http); prod enforces https.
