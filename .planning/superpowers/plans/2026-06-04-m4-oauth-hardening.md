# M4 — jvspatial OAuth 2.1 Hardening — Spec + Plan

> superpowers:subagent-driven-development. TDD. Security-critical (shared OAuth lib) → security review (M4-T6). Branch jvspatial `feat/m4-oauth-hardening` (off `feat/m3-authorize-redirect`). Integral editable-installs jvspatial → picks these up live; M4-T6 re-verifies integral's oauth/mcp suites.

**Goal:** close the latent OAuth hardening items surfaced in M2b/M3 reviews. Secure-by-default where a scope ceiling is declared; back-compat preserved when not.

> ⚠️ **COMMIT DISCIPLINE:** jvspatial tree has unrelated doc edits + the M3a commit; explicit pathspec per commit. NEVER `git add -A`. NO `--no-verify`.

> **Grounded facts** (file:line): `_intersect_scope` `server.py:236-255` (guard `if not permissions:` → no narrowing); single callsite `save_authorization_code` `server.py:363-367` (`permissions = request.user.get("permissions") or None` collapses `[]`→`None`); `build_authorization_server(issuer, resource)` `server.py:758` (constructs `scopes_supported=None` `:776`); `oauth_supported_scopes` declared `config_groups.py:269`, consumed only for metadata `routes.py:183,193`. DCR `save_client` `dcr.py:186` (scope verbatim). Rate-limit backend Protocol `rate_limit_backend.py:12-50` (pluggable; `RedisRateLimitBackend:163` exists); selected `server_configurator.py:104-116` (`getattr(server.config,'rate_limit_backend',None)` — NOT a declared field); `_get_client_identifier` `rate_limit.py:68-99` (`ip:user_agent` hash); `_wire_dcr_rate_limit` `auth_configurator.py:639-685`. Auth-code consume `server.py:408-448` (`_consume_code` blind `consumed=True;save()`; TOCTOU note `:421-425`); `find_one_and_update`/`find_one_and_delete` atomic on postgres (`postgres.py:1020`) + mongo, best-effort base; CAS idiom `work_claim.py:33-104`. `jti` already set by Authlib generator (jvspatial `JvSpatialJWTTokenGenerator` `server.py:276-325` doesn't override `get_jti`); RS `verify_oauth_access_token` `resource.py:33-60` (require `exp,iss,aud,sub` — no jti). Revocation refresh-only `revocation.py`. rbac `DEFAULT_ROLE_PERMISSION_MAPPING={"admin":["*"],"user":[]}` `rbac.py:5-8`. Tests under `tests/api/auth/oauth/` + `tests/api/middleware/` + `tests/api/test_rate_limiting.py`.

---

## M4-T1 — Scope-ceiling plumbing + Item 1 (empty-perms) + Item 8 (`*` wildcard)
**Files:** `jvspatial/api/auth/oauth/server.py` (`build_authorization_server`, the server class, `_intersect_scope`, `save_authorization_code`), `jvspatial/api/auth/oauth/routes.py` (pass `oauth_supported_scopes` into `build_authorization_server`); tests `tests/api/auth/oauth/test_oauth_server_flow.py` (extend).
- **Plumbing:** add `supported_scopes: Optional[List[str]] = None` param to `build_authorization_server`; store on the server (alongside `_resource`, e.g. `_supported_scopes`). `routes.py:173` passes `auth_config.oauth_supported_scopes`. (Also reachable for T2.)
- **Item 1 — empty-perms discriminator:** `_intersect_scope` guard `if permissions is None:` (absent ⇒ no narrowing, back-compat) vs `[]` (present-but-empty ⇒ narrow to nothing). In `save_authorization_code` remove the `or None` coercion (`server.py:366`) so a present `[]` stays `[]`.
- **Item 1 — supported-scopes ceiling:** in `save_authorization_code`, after the permission intersection, also intersect against `self._supported_scopes` WHEN it's non-empty (empty ⇒ no ceiling, back-compat). Net: `granted = requested ∩ (supported if supported else ⊤) ∩ (perms-rule)`.
- **Item 8 — `*` wildcard:** in `_intersect_scope`, if `"*" in permissions` → treat as "all permissions" = return the requested scope (which `save_authorization_code` then ceilings to `_supported_scopes`). So an admin (`["*"]`) gets requested ∩ supported (not empty, not unbounded). MUST land WITH the ceiling (else `*` over-grants).
- **TDD:** (a) absent permissions key → no narrowing (existing `test_scope_unfiltered_when_no_permissions_provided` stays green via `is None`); (b) **present `[]` → empty granted scope** (NEW — the zero-permission footgun); (c) existing intersection test green; (d) **admin `["*"]` + supported `["mcp"]` requesting `"mcp admin"` → granted `"mcp"`** (NEW — inverted-admin footgun fixed, bounded by supported); (e) supported empty → ceiling no-op (back-compat). Run the oauth-flow + authorize-http slices.
- Commit — `feat(oauth): supported-scope ceiling + empty-perms/wildcard scope hardening`. CHANGELOG note (empty-perms ⇒ deny is a behavior change for any out-of-tree caller passing `permissions:[]` expecting full grant).

## M4-T2 — Item 2: DCR filters registered scope against supported
**Files:** `jvspatial/api/auth/oauth/dcr.py` (`save_client` / `extract_client_metadata`), maybe `get_server_metadata` (advertise `scopes_supported`); test `tests/api/auth/oauth/test_oauth_dcr.py`.
- Read `_supported_scopes` off the server (threaded in T1). In `save_client`: `scope = " ".join(s for s in requested.split() if s in supported)` when supported non-empty; else verbatim (back-compat). Silent-filter (gentler for zero-config MCP clients) — RFC 7591 permits.
- Optionally add `scopes_supported` to `get_server_metadata`.
- **TDD:** client registering `scope:"mcp admin"` with supported `["mcp"]` → persisted `OAuthClient.scope == "mcp"`; supported empty → verbatim. CHECK `test_oauth_dcr.py:47`'s server build sets supported to include `mcp` (or empty) so it stays green; adjust the test's expectation if it now filters.
- Commit — `feat(oauth): DCR filters requested scope against supported scopes`.

## M4-T3 — Item 4: auth-code consume CAS (multi-worker TOCTOU)
**Files:** `jvspatial/api/auth/oauth/server.py` (`_consume_code` / `delete_authorization_code`); test `tests/api/auth/oauth/test_oauth_server_flow.py`.
- Replace the blind `consumed=True; save()` with an atomic conditional update: `find_one_and_update(collection, {"_id": record_id, "context.consumed": False}, {"$set": {"context.consumed": True}})` (mirror `work_claim.py`). A `None`/no-match result ⇒ lost the race ⇒ the exchange MUST fail (raise the same error a consumed code raises). Atomic on postgres (integral default) + mongo; best-effort base (sqlite/json) — no regression vs today. Keep the consume AFTER PKCE+redirect validation (don't burn on failed verifier — `test_failed_verifier_does_not_burn_code_for_retry` stays green).
- **TDD:** existing single-use + failed-verifier tests green; NEW: two concurrent consumes of the same code → exactly one succeeds, the other rejected (simulate via two `find_one_and_update` calls; assert the second returns no-match → rejection). Update the `server.py:421-425` note to reflect CAS-on-supporting-backends.
- Commit — `fix(oauth): atomic auth-code consume (CAS) to close multi-worker TOCTOU`.

## M4-T4 — Item 7a (rate-limit key) + Item 3 (pluggable backend first-class)
**Files:** `jvspatial/api/middleware/rate_limit.py` (`_get_client_identifier`), `jvspatial/api/config.py` or `config_groups.py` (declare `rate_limit_backend`), `jvspatial/api/components/server_configurator.py` (read the declared field); tests `tests/api/test_rate_limiting.py`, `tests/api/middleware/test_rate_limit_backend.py`.
- **7a:** drop `user_agent` from `_get_client_identifier` — IP-only key (`user_agent` is attacker-controlled → rotates to evade). Authenticated `user:{id}` path unchanged.
- **3:** declare `rate_limit_backend` as a first-class optional field (mirror the `create_session_store()` precedent) so swapping to `RedisRateLimitBackend` is documented + typed (default `None` → `MemoryRateLimitBackend`, unchanged). Document the multi-worker `cap × workers` limitation for the in-memory backend (in the field docstring + CHANGELOG; the DCR limit inherits it).
- **TDD:** `_get_client_identifier` no longer varies by user-agent (same IP + different UA → same key); existing 429-burst test green; the declared backend field defaults correctly.
- Commit — `feat(ratelimit): IP-only identifier + first-class pluggable backend`.

## M4-T5 — Item 6: jti denylist (revoke access tokens before expiry)
**Files:** `jvspatial/api/auth/oauth/models.py` (+`OAuthRevokedToken{jti, expires_at}` Object), new `jvspatial/api/auth/oauth/denylist.py` (or extend `refresh_store.py`), `jvspatial/api/auth/oauth/resource.py` (`verify_oauth_access_token` checks denylist), `jvspatial/api/auth/oauth/revocation.py` (accept `token_type_hint=access_token` → decode + denylist the jti); test `tests/api/auth/oauth/test_oauth_revocation.py`.
- `OAuthRevokedToken` Object (jti + self-expiring `expires_at` = the token's own `exp`), mirroring `OAuthRefreshToken`. Denylist store: `revoke_jti(jti, expires_at)` + `is_jti_revoked(jti)` (indexed lookup; optional short-TTL in-proc cache — note the hot-path cost).
- `verify_oauth_access_token`: after decode, `if claims.get("jti") and await is_jti_revoked(claims["jti"]): return None`. Add `jti` to the `require` list (tokens already carry it).
- `/oauth/revoke`: when the presented token is a JWT access token (or `token_type_hint=access_token`), validate it (sig/iss/aud), insert its `jti`+`exp` into the denylist. Keep refresh-token revocation as-is.
- **Integral benefit:** M3's connected-agents revoke kills refresh tokens; this makes the access token die immediately too (the agent can't keep acting for up to the TTL). Note: integral's `revoke_connected_agent` could later also denylist the agent's active access-token jtis — out of M4 scope (integral side), but the capability now exists.
- **TDD:** mint a token → it validates; revoke its jti → `verify_oauth_access_token` now returns None (rejected); a different token's jti unaffected; denylist row self-expires (or is harmless after exp). Mirror the refresh-reuse test pattern.
- Commit — `feat(oauth): jti denylist for access-token revocation before expiry`.

## M4-T6 — verification + security review + document deferrals
- **jvspatial suite** green (oauth + middleware slices + broad; the `tests/storage/*` libmagic failures are pre-existing/unrelated).
- **integral suite** (editable-install picks up M4): run integral `backend/tests/test_oauth_consent.py test_connected_agents.py test_mcp_server_*.py` + a broad slice — confirm the scope-ceiling change doesn't break integral's flow (integral sets `oauth_supported_scopes=["integral"]`, so its tokens ceiling to `integral` — the M3 zero-permission test + escalation tests should still pass; the M3 integral-side bound becomes belt+suspenders). Re-run integral's full backend suite if feasible.
- **Document deferrals** in jvspatial CHANGELOG + the OAuth security-review doc: **Item 5** (RFC-8707 per-request resource→aud — single-resource deploys correct as-is; seam present for multi-resource later) and **Item 7b** (trusted-XFF parsing — needs a `trusted_proxies`/`proxy_hops` config; unconditional XFF trust is a spoof vector, so deferred until that knob lands).
- **Independent security review:** the scope ceiling (no over-grant for zero-perms/admin/`*`; back-compat when supported empty), DCR filter, the CAS (no double-spend, no burn-on-failed-verifier regression), the rate-limit key (no UA-rotation evasion), the jti denylist (revoked access token rejected; no bypass; the require-jti change doesn't reject pre-existing valid tokens — they all carry jti). Confirm no new auth-bypass + back-compat for non-scope consumers.

## Self-Review
- Coupling: T1 plumbing feeds T2 + T8(in T1). T1 must land first. T3/T4/T5 independent.
- Back-compat: every ceiling/filter is a no-op when `oauth_supported_scopes` empty (default) → existing non-scope consumers unaffected. The one behavior change (empty-perms `[]` ⇒ deny) is documented; jvspatial's own routes never rely on the old meaning.
- Deferrals (5, 7b) documented with rationale, not silently skipped.
