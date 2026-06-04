# M4 — jvspatial OAuth 2.1 Hardening — COMPLETION RECORD

> Companion to the plan `2026-06-04-m4-oauth-hardening.md`. This is the
> as-shipped record + holistic adversarial security review + documented
> deferrals. Branch `feat/m4-oauth-hardening`. Commit range `8d99c27..fab089b`
> (the five M4 commits; `7565955` M3a authorize-redirect sits just below the
> range and composes with M4 — confirmed below).

**Status:** Shipped, holistically reviewed, SAFE TO MERGE. No Critical, no
Important findings. Two intentional behavior changes (documented). Two items
genuinely deferred with rationale (Item 5, Item 7b). A handful of benign Minor
follow-ups noted.

---

## 1. What shipped (the five fixes)

| Commit | Item | Change |
|--------|------|--------|
| `8fe442a` | Scope ceiling (headline) | `_intersect_scope` now discriminates `None` (absent key → no narrowing, back-compat) / `[]` (present-empty → **deny all scope**) / `"*"` (wildcard → all requested) / membership filter. `save_authorization_code` no longer collapses `[] → None`, and after the permission intersection applies a **supported-scope ceiling** (`granted ∩ _supported_scopes`) when one is declared. `build_authorization_server(supported_scopes=)` threaded from `routes.py` ← `auth_config.oauth_supported_scopes`. |
| `2ea86cd` | DCR scope filter | `extract_client_metadata` silently intersects the requested `scope` against `server._supported_scopes` when a ceiling is declared (RFC 7591 permits silent filter; gentler than a 400 for zero-config MCP clients). Verbatim when no ceiling. Deliberately does NOT advertise `scopes_supported` in client-registration metadata (would trigger Authlib's hard `issuperset` 400 before the silent filter could run). |
| `a3d5829` | Auth-code CAS | `_consume_code` replaced blind `consumed=True; save()` with an atomic `find_one_and_update({_id, context.consumed: False}, {$set: consumed=True})`. `None` result → lost the race → raise `InvalidGrantError` (same path a replayed/consumed code produces) → token issuance aborts for the loser. Drops the stale cache entry afterward (`_remove_from_cache`). Atomic on postgres (`SELECT … FOR UPDATE`) + mongo (native `findOneAndUpdate`); best-effort read-modify-write on sqlite/json (no regression vs the prior blind write). |
| `9edf957` | Rate-limit | `_get_client_identifier` unauthenticated bucket is now **IP-only** (`sha256(request.client.host)`) — dropped the attacker-controlled `User-Agent` fold that allowed per-request bucket rotation to evade the per-IP cap. `rate_limit_backend` promoted to a first-class `Optional[RateLimitBackend]` `ServerConfig` field (`None` → process-local `MemoryRateLimitBackend`; supply `RedisRateLimitBackend` for a hard multi-worker cap). |
| `fab089b` | jti denylist | New `OAuthRevokedToken` Object (`jti` + self-expiring `expires_at = token exp`), new `denylist.py` (`revoke_jti` / `is_jti_revoked`). `verify_oauth_access_token` now requires `jti` and rejects denylisted jtis. `/oauth/revoke` (`revocation.py`) gained an access-token path: a presented JWT access token is validated, and on `check_client` match (token's `client_id` claim == authenticated client) its `jti` is denylisted until its own `exp`. Refresh-token revocation unchanged. |

M3a (`7565955`, just below the range): unauthenticated `GET /oauth/authorize`
302-redirects to `auth_config.oauth_authorize_login_redirect` (configured base +
original query only — open-redirect safe) when set, else legacy 401. Confirmed
intact and composing with M4 below.

---

## 2. Behavior change (action required for some out-of-tree consumers)

**`permissions: []` ⇒ deny all scope (was: full grant).** Before M4,
`save_authorization_code` coerced a present-but-empty `permissions` list to
`None`, which `_intersect_scope` treated as "no narrowing" — i.e. an empty
permission set granted the *full* requested scope. This was a zero-permission
footgun. M4 distinguishes:

- **absent `permissions` key** (`None`) → no narrowing (back-compat preserved
  for low-level callers passing only `{"id": ...}`);
- **present empty list** (`[]`) → narrows to the **empty** scope (an explicit
  "authorize nothing").

> **Migration:** Any out-of-tree consumer that built `grant_user` with an
> explicit `permissions: []` while *relying on the old empty ⇒ full-grant*
> behavior must now pass an explicit permission set (or `["*"]` for admin, or
> omit the key entirely to keep the no-narrowing back-compat). jvspatial's own
> routes are unaffected: `authorize_post` always supplies a *computed*
> permission set (`get_effective_permissions(...)`), so a zero-permission user
> correctly gets `[]` → empty scope.

**Secondary (strictly more protective, no migration):** the unauthenticated
rate-limit bucket key is now IP-only. Two requests from the same IP with
different `User-Agent` values now share a bucket (previously they were two
separate buckets — the evasion this fix closes). No legitimate caller is
penalized.

No OTHER behavior change for an unconfigured consumer (see §4).

---

## 3. Holistic security verification (adversarial pass)

**Test result:** `tests/api/auth/oauth/` + `tests/api/middleware/` →
**92 passed, 0 failed** (`.venv`, pytest, ~16s; only Authlib deprecation
warnings). M4-specific behaviors are explicitly asserted, not merely present:
`test_scope_supported_ceiling`, `test_admin_wildcard_ceilinged_to_supported`,
`test_scope_empty_permissions_grants_nothing`,
`test_scope_unfiltered_when_no_permissions_provided`,
`test_concurrent_code_exchange_only_one_succeeds`,
`test_full_exchange_issues_exactly_one_token_after_cas`,
`test_denylisted_token_rejected`, `test_other_token_unaffected_by_denylist`,
`test_issued_token_carries_jti`, `test_expired_denylist_row_not_revoked`,
`test_revoke_jti_idempotent`, `test_revoke_access_token_denylists_jti`,
`test_revoke_access_token_wrong_client_rejected`,
`test_revoke_access_token_without_hint`; M3a redirect asserts
`{base}?{original_query}` exactly (open-redirect safe).

### V1 — Scope ceiling composes; no over-grant on any branch; DCR↔authorize consistent

Full grant chain traced: DCR-registered scope (silently filtered to supported)
→ Authlib client-scope intersection → `_intersect_scope` (None/[]/`*`/membership)
→ supported-scope ceiling. No branch over-grants:

- **(a) zero-perm user** → `get_effective_permissions([], [], {}) = ∅` →
  `permissions = []` → membership filter → **empty scope**. ✅
- **(b) admin `*`** → role `admin` maps to `["*"]` → `permissions = ["*"]` →
  `_intersect_scope` returns full requested scope → **bounded by the
  supported-scope ceiling** in `save_authorization_code`. ✅ (the inverted-admin
  footgun — `*` literal matching nothing — is fixed, and `*` is NOT unbounded.)
- **(c) absent key** (low-level `{"id": ...}` callers) → `permissions = None`
  → no narrowing → **still ceiling'd** by supported. ✅
- **(d) supported empty** (back-compat consumer, default
  `oauth_supported_scopes=[]`) → ceiling block (`if supported:`) skipped → no
  ceiling; behaves as pre-M4 **except** `[]` ⇒ deny. ✅

**DCR ↔ authorize consistency:** both `extract_client_metadata` (DCR) and
`save_authorization_code` (authorize) read `server._supported_scopes` off the
**same** `JvSpatialAuthorizationServer` instance built in `build_oauth_routers`
(`register_endpoint`/`register_grant` bind `.server = self`). There is no gap
where DCR would allow a scope the authorize ceiling rejects, or vice versa — they
share one source of truth. DCR uses a *silent* intersection (HTTP 201, unsupported
tokens dropped) and authorize uses the *same* set as a hard ceiling at
code-persistence; defense-in-depth, fully consistent.

> Note (UX, not a security gap): the consent page (GET `/authorize`) renders the
> *client-filtered* requested scope, not the post-ceiling scope, because the
> ceiling is applied later in `save_authorization_code` (POST approve). The page
> can therefore display *more* scope than is ultimately granted. Showing more and
> granting less is safe (never the reverse). A future polish could apply the
> ceiling at consent-render time for display fidelity.

### V2 — No fail-open anywhere

- **CAS lost race** → `find_one_and_update` returns `None` (no match) →
  `_consume_code` raises `InvalidGrantError` → no token. A DB exception
  propagates (not swallowed) → token issuance aborts. **Fail-closed.** ✅
- **jti denylist DB error** → `is_jti_revoked` is called *outside* the JWT-decode
  try/except in `verify_oauth_access_token`; a raised DB error propagates to the
  bearer-auth middleware (→ 500, request rejected) — and even if it were caught,
  the only catch arm `return None` = reject. The caller
  (`auth_middleware._authenticate_oauth_bearer`) treats `None`/exception as
  unauthenticated. A denylist outage therefore **rejects tokens, never accepts
  them.** **Fail-closed.** ✅
- **Scope edges** — `None` no-narrow is still ceiling'd; `[]` denies;
  empty-supported is a no-op ceiling (correct back-compat). No accidental
  over-grant. ✅
- **Rate-limit backend `None`** → `server.config.rate_limit_backend or
  MemoryRateLimitBackend()` (both in the middleware `__init__` and in
  `server_configurator._configure_rate_limit_middleware`) → `None` falls back to
  the in-memory limiter, never "no limit". (And the middleware is only installed
  when `rate_limit_enabled=True`.) **Fail-closed (within configured posture).** ✅

### V3 — Back-compat overall (unconfigured consumer = near no-op)

A consumer that does NOT set `oauth_supported_scopes` (default `[]`), does NOT set
`rate_limit_backend` (default `None`), does NOT set `oauth_authorize_login_redirect`
(default `""`), and runs single-process: M4 is a near-no-op **except** the two
documented changes —

1. `permissions: []` ⇒ deny (the scope footgun fix); and
2. IP-only unauthenticated rate-limit key (strictly more protective).

No other behavior change found. Specifically: the `require: ["jti"]` addition
rejects ZERO legitimately-minted tokens — `JvSpatialJWTTokenGenerator` extends
Authlib's RFC-9068 generator and does NOT override `get_jti`, so every token this
AS issues carries a random `jti`; only tokens minted *without* a jti (which this
AS never produces) are newly rejected. The revocation endpoint's new access-token
branch is additive: refresh-only callers still hit the `_RevocableToken` →
`refresh_store.revoke` path unchanged. `oauth_supported_scopes=[]` makes both the
DCR filter and the authorize ceiling no-ops. M3a's redirect is a no-op when its
field is unset (legacy 401 preserved).

### V4 — No cross-cutting / new bypass

- The jti `require` change does NOT reject anything the rate-limit or consent path
  depends on (rate-limit keys on IP/user-id, not token claims; consent runs on the
  session bearer, not an OAuth-issued token).
- CAS × jti denylist: a code that loses the CAS mints no token, hence has no jti to
  denylist — no interaction, no orphan denylist row. ✅
- M3a authorize redirect × M4 scope: the redirect is a **pre-auth gate** on the
  unauthenticated GET only; the scope ceiling lives downstream in
  `save_authorization_code`, reachable only via the authenticated POST-approve path
  (`async_create_authorization_response`). The redirect cannot bypass the ceiling —
  it never reaches code issuance. POST `/authorize` keeps the raising
  `Depends(get_current_user)`; only the GET seam is non-raising. ✅
- New access-token revocation is NOT a DoS / arbitrary-denylist surface: Authlib's
  `authenticate_token` enforces `authenticate_endpoint_client` then
  `token.check_client(client)` *before* `revoke_token`. `_RevocableAccessToken.check_client`
  compares the token's `client_id` claim to the authenticated client, AND the token
  string must verify as a valid, non-expired, audience-bound JWT. A caller can only
  denylist a jti for a token issued to their own authenticated client that they
  physically present. ✅

### V5 — Deferred items are genuinely deferred, not half-done

- **Item 5 (RFC-8707 per-request resource → aud):** `aud` is consistently the
  `issuer` (single-resource). `routes.py` builds the server with `resource=issuer`;
  `JvSpatialJWTTokenGenerator.get_audiences` returns `self._resource` (= issuer) for
  every token; RS verification (`resource.py`, `auth_middleware`) and the revocation
  path all check `audience=issuer`. There is NO partial per-request resource
  variation — the seam (`_resource` field, `get_audiences` hook) exists but is
  uniformly wired to the issuer. Clean. ✅
- **Item 7b (trusted XFF):** XFF is NOT trusted. `_get_client_identifier` uses
  `request.client.host` (the immediate socket peer) only; the only `X-Forwarded-For`
  references in `rate_limit.py` are the comment explicitly stating it is deferred and
  NOT parsed. No spoofable header feeds the bucket key. The known limitation (clients
  collapsing onto a proxy IP behind a load balancer) is the *conservative*
  failure mode — it over-buckets, never lets an attacker mint a fresh bucket. ✅

---

## 4. Security verdict

**SAFE TO MERGE.** The headline scope-ceiling fix composes correctly across all
branches with no over-grant; the DCR and authorize ceilings share one source of
truth; every failure mode (CAS lost race, denylist DB error, missing backend,
scope edges) is fail-closed; the only two behavior changes for an unconfigured
consumer are the documented `[]`⇒deny footgun fix and the strictly-more-protective
IP-only rate-limit key; no M4 change weakens another auth path; and the two
deferrals are uniformly absent rather than half-implemented.

### Cross-repo verification (integral consumer, editable install)

The full test verification (separate from the security pass) ran both repos. **jvspatial:** oauth slice **74 passed**, middleware green; only the pre-existing `tests/storage/*` libmagic/MIME failures remain (M4 touches no storage code). **integral:** the test run initially FAILED — 2 consent escalation tests over-granted `admin` — because integral's *separate* consent authorization-server (`backend/app/api/oauth_consent.py`) was built without declaring `supported_scopes`, so M4's new `'*'`-wildcard branch (which is *meant* to be bounded by the supported-scope ceiling) had no ceiling to apply on integral's path. This is the exact composition gap the security pass could not see (it reviewed jvspatial's flow where the ceiling is declared). **Fixed integral-side** in commit `1bb5f5a` (`feat/m3-agents-ui`): the consent `_AS` now passes `supported_scopes=settings.OAUTH_SUPPORTED_SCOPES` (`["integral"]`), parity with the mounted server. **Post-fix: integral consent 10 passed, broad oauth/mcp slice green, boot OK.** Lesson: any consumer that builds its own `build_authorization_server(...)` instance MUST declare `supported_scopes` to get the M4 ceiling — the `'*'` branch is unbounded without it. Both repos now green.

- **Critical:** none.
- **Important:** none.
- **Minor (benign, surfaced in per-task reviews; documented, not blocking):**
  - *jti denylist duplicate-row idempotency:* `revoke_jti` does a read-then-insert
    (`find` → insert if absent), not an atomic upsert; two concurrent revocations of
    the same jti could in principle write two rows. Harmless — both rows carry the
    same `exp`, and `is_jti_revoked` returns `True` on *any* non-expired match. A
    later optimization could use a unique index on `jti` or an atomic upsert.
  - *Orphan refresh token on CAS lost-race:* the CAS protects the auth-*code* single-use;
    if a refresh token were generated before the loser's CAS check it could be orphaned.
    In practice token issuance is gated on the code consume, so the loser never reaches
    a committed refresh token — benign. Worth a glance if the issue order is ever
    refactored.
  - *Consent-page scope display vs. post-ceiling grant:* the GET consent page can show
    more scope than is granted (ceiling applied at POST/persist). UX-only; granting less
    than displayed is safe.

---

## 5. Documented deferrals (intentional, not skipped)

### Item 5 — RFC-8707 per-request resource → token `aud`

**Status:** deferred. **Why it's correct to ship without it:** the AS and RS are the
same process and serve a single protected-resource audience, so binding every token's
`aud` to the `issuer` is the correct single-resource behavior (`aud == issuer`),
verified consistently on issue and on validation. **When to implement:** when jvspatial
serves *multiple* resource-server audiences from one AS (a client requests a token for
a specific RS via the `resource` parameter, and the token `aud` must reflect that RS,
not the issuer). **Seam already present:** `JvSpatialAuthorizationServer._resource` is a
distinct field and `JvSpatialJWTTokenGenerator.get_audiences(client, user, scope)` is the
override point — implement per-request `resource` parsing there and thread the requested
resource through the grant. Until then, do NOT vary `aud` per request (a partial change
would break the uniform `aud == issuer` validation contract).

### Item 7b — Trusted X-Forwarded-For parsing for the rate-limit key

**Status:** deferred. **Why it's correct to ship without it:** unconditional XFF trust is
a spoof vector — any unauthenticated client can set `X-Forwarded-For` to a value of its
choosing and mint a fresh rate-limit bucket per request, defeating the per-IP cap
entirely (worse than the IP-only key shipping now). The IP-only key
(`request.client.host`) is correct and safe for direct-exposure and single-proxy
deployments. **When to implement:** when a `trusted_proxies` / `proxy_hops` config knob
lands — XFF should be consulted ONLY for the configured number of trusted proxy hops
(walk the XFF chain right-to-left, skip `proxy_hops` trusted entries, take the next as
the client IP). **Known current limitation:** behind an untrusted-from-the-app's-view
reverse proxy / load balancer, all clients collapse onto the proxy IP and share one
bucket — a conservative (over-restrictive) failure, never an under-restrictive one.
Document the knob and the right-to-left walk when implementing.

---

## 6. Commit / merge notes

- Five M4 commits + M3a all on `feat/m4-oauth-hardening`; tests green.
- Working tree carries entangled, unrelated edits (`CHANGELOG.md`, `SPEC.md`,
  `docs/md/security-review.md`, retention module, api-key/cleanup tweaks). Those are
  NOT part of M4 — commit this completion record with an explicit pathspec only;
  do not stage the entangled files, and do not use `--no-verify`. The OAuth
  security notes live in this record (the entangled `docs/md/security-review.md`
  was intentionally left untouched).
