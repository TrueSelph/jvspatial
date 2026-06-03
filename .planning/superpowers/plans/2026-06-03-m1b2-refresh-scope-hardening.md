# M1b-2 — Refresh grant + scope∩permissions + token hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps. **Security-critical** (auth) — the refresh/rotation tasks get a security review.

**Goal:** Add OAuth refresh-token issuance + rotation (persisted, revocable), restrict granted scope to the user's effective permissions, and close the two hardening gaps from the M1b-1 review (single-use-code TOCTOU, missing `nbf`).

**Architecture:** Extends the M1b-1 `build_authorization_server` (anyio-bridged Authlib AS). Refresh tokens are opaque, hashed, stored in the M1a `RefreshToken` Object (extended with OAuth fields); the RFC-9068 JWT generator gains a `refresh_token_generator`; a `RefreshTokenGrant` validates+rotates them. Scope is intersected with `get_effective_permissions` at code issuance. Consent UI + `/authorize` session resolution + HTTP route mounting are **M1b-3** (not here).

**Tech Stack:** authlib 1.7.2 (`RefreshTokenGrant`, `JWTBearerTokenGenerator(refresh_token_generator=...)`), jvspatial `RefreshToken`/RBAC, anyio bridge (M1b-1). venv `.venv`. Pre-commit: black/isort/flake8(D-codes)/mypy/detect-secrets.

**Repo/branch:** jvspatial `feat/oauth2-service` (M1a + M1b-1 committed: HEAD `fc785cb`).

> **RUNTIME-VALIDATION:** Tasks 2–3 wire Authlib's refresh path — verify against installed source (`.venv/.../authlib/oauth2/rfc6749/grants/refresh_token.py`, `rfc9068/token.py`) and adapt method names/flow to 1.7.2; the tests pin observable behavior.

---

## Confirmed facts (from installed authlib 1.7.2)
- `JWTBearerTokenGenerator.__init__(self, issuer, alg='RS256', refresh_token_generator=None, expires_generator=None)`.
- `RefreshTokenGrant`: implement `authenticate_refresh_token(self, refresh_token)`, `authenticate_user(self, credential)`, `revoke_old_credential(self, refresh_token)`; class attr `INCLUDE_NEW_REFRESH_TOKEN=False` → set `True` for rotation; `TOKEN_ENDPOINT_AUTH_METHODS` (include `"none"` for public clients).
- M1a `RefreshToken(Object)` fields: `token_hash, token_lookup, user_id, access_token_jti, expires_at, is_active, created_at, last_used_at, device_info, ip_address`.

---

## File Structure
- `jvspatial/api/auth/oauth/models.py` — *modify*: add `client_id`/`scope`/`resource` to `RefreshToken`? NO — `RefreshToken` lives in `jvspatial/api/auth/models.py` (shared). To avoid disturbing the session-auth model, define a dedicated **`OAuthRefreshToken(Object)`** in `oauth/models.py` instead (cleaner isolation; OAuth refresh ≠ session refresh).
- `jvspatial/api/auth/oauth/refresh_store.py` — *create*: hash + persist/lookup/revoke helpers over `OAuthRefreshToken` (async).
- `jvspatial/api/auth/oauth/server.py` — *modify*: `save_token` persistence, `refresh_token_generator`, `JvSpatialRefreshTokenGrant`, scope∩permissions at code issue, single-use atomic consume, `nbf` via `get_extra_claims`.
- tests under `tests/api/auth/oauth/`.

DECISION: use a dedicated `OAuthRefreshToken` (not the shared session `RefreshToken`) — isolates OAuth from session-auth and carries `client_id`/`scope`/`resource` without touching `jvspatial/api/auth/models.py`. (Supersedes the spec's "reuse RefreshToken" note; record the deviation.)

---

## Task 1: `OAuthRefreshToken` model + refresh store

**Files:** modify `oauth/models.py` (add model); create `oauth/refresh_store.py`; test `tests/api/auth/oauth/test_oauth_refresh_store.py`.

- [ ] **Step 1: failing test**:
```python
"""OAuthRefreshToken store: mint (hashed) -> lookup by token -> revoke."""

import tempfile
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.db.factory import create_database
from jvspatial.api.auth.oauth import refresh_store


@pytest.fixture
def temp_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        database = create_database("json", base_path=f"{tmpdir}/t_{uuid.uuid4().hex}")
        context = GraphContext(database=database)
        set_default_context(context)
        yield context


@pytest.mark.asyncio
async def test_mint_lookup_revoke(temp_context):
    plaintext = await refresh_store.mint_refresh_token(
        token="rt_secret_value", user_id="u_1", client_id="cli_1",
        scope="mcp", resource="https://api.example/mcp",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    assert plaintext == "rt_secret_value"  # stored hashed, returns what it stored

    found = await refresh_store.find_active("rt_secret_value")
    assert found is not None
    assert found.user_id == "u_1"
    assert found.client_id == "cli_1"
    assert found.is_active is True

    # wrong token does not match
    assert await refresh_store.find_active("nope") is None

    await refresh_store.revoke(found)
    assert await refresh_store.find_active("rt_secret_value") is None
```

- [ ] **Step 2: run, verify FAIL.**

- [ ] **Step 3: add `OAuthRefreshToken` to `oauth/models.py`** (append):
```python
class OAuthRefreshToken(Object):
    """An OAuth refresh token (opaque, stored hashed). Distinct from the
    session-auth RefreshToken so OAuth carries client/scope/resource."""

    token_hash: str = Field(..., description="SHA-256 hash of the refresh token")
    user_id: str = Field(..., description="Resource-owner user id")
    client_id: str = Field(..., description="Owning client_id")
    scope: str = Field(default="", description="Granted scope (space-delimited)")
    resource: Optional[str] = Field(default=None, description="Audience/resource")
    expires_at: datetime = Field(..., description="Expiry")
    is_active: bool = Field(default=True, description="False once revoked/rotated")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )
```

- [ ] **Step 4: create `oauth/refresh_store.py`**:
```python
"""Async persistence for OAuth refresh tokens (opaque, stored SHA-256 hashed)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from jvspatial.api.auth.oauth.models import OAuthRefreshToken


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def mint_refresh_token(
    *, token: str, user_id: str, client_id: str, scope: str,
    resource: Optional[str], expires_at: datetime,
) -> str:
    """Persist a refresh token (hashed) and return the plaintext (caller emits it)."""
    rec = OAuthRefreshToken(
        token_hash=_hash(token), user_id=user_id, client_id=client_id,
        scope=scope or "", resource=resource, expires_at=expires_at, is_active=True,
    )
    await rec.save()
    return token


async def find_active(token: str) -> Optional[OAuthRefreshToken]:
    """Return the active, unexpired token record for ``token`` or None."""
    rows = await OAuthRefreshToken.find(
        {"context.token_hash": _hash(token), "context.is_active": True}
    )
    if not rows:
        return None
    rec = rows[0]
    exp = rec.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        return None
    return rec


async def revoke(rec: OAuthRefreshToken) -> None:
    """Mark a refresh token inactive (revocation / rotation)."""
    rec.is_active = False
    await rec.save()
```

- [ ] **Step 5: PASS. Step 6: lint + commit** `oauth/models.py oauth/refresh_store.py test_oauth_refresh_store.py` → `feat(oauth): OAuthRefreshToken model + refresh store`.

---

## Task 2: Issue refresh tokens on the auth-code flow (`save_token` + refresh generator)

**Files:** modify `oauth/server.py`; test add to `tests/api/auth/oauth/test_oauth_server_flow.py`.

- [ ] **Step 1: failing test** (append):
```python
@pytest.mark.asyncio
async def test_authcode_flow_issues_persisted_refresh_token(temp_context):
    import secrets, hashlib, base64
    await keystore.ensure_signing_key()
    await OAuthClient(
        client_id="cli_pub", client_secret_hash=None,
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"], scope="mcp", token_endpoint_auth_method="none",
    ).save()
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    a = StarletteOAuth2Request(
        method="POST", uri=f"{ISSUER}/oauth/authorize",
        query={"response_type": "code", "client_id": "cli_pub",
               "redirect_uri": "https://c.example/cb", "scope": "mcp",
               "code_challenge": challenge, "code_challenge_method": "S256"},
        form={}, headers={})
    from urllib.parse import urlparse, parse_qs
    r = await server.async_create_authorization_response(a, grant_user={"id": "u_1"})
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    t = StarletteOAuth2Request(
        method="POST", uri=f"{ISSUER}/oauth/token", query={},
        form={"grant_type": "authorization_code", "code": code,
              "redirect_uri": "https://c.example/cb", "client_id": "cli_pub",
              "code_verifier": verifier}, headers={})
    body = (await server.async_create_token_response(t)).body_json
    assert body.get("refresh_token")  # refresh token issued
    from jvspatial.api.auth.oauth import refresh_store
    assert await refresh_store.find_active(body["refresh_token"]) is not None  # persisted
```

- [ ] **Step 2: FAIL** (no refresh_token in body yet).
- [ ] **Step 3: implement.** In `server.py`:
  - Add a `refresh_token_generator` (e.g. `lambda *a, **k: "rt_" + secrets.token_urlsafe(48)`) and pass it to `JvSpatialJWTTokenGenerator(issuer=..., refresh_token_generator=...)`. Confirm RFC-9068 generator includes the refresh token in its output when the grant requests it (read `rfc9068/token.py` / `rfc6750` base — the `__call__` includes refresh when `include_refresh_token` and a generator is set; the auth-code grant requests it for clients allowing `refresh_token`).
  - Implement `save_token(self, token, request)` to persist the refresh token: if `token.get("refresh_token")`, `call_async(refresh_store.mint_refresh_token, token=token["refresh_token"], user_id=<request.user id>, client_id=request.client.get_client_id(), scope=token.get("scope",""), resource=self._resource, expires_at=now + refresh_ttl)`. (Access token is a stateless JWT — nothing to persist for it.)
  - RUNTIME-VALIDATION: confirm how/whether the auth-code grant triggers refresh issuance (the client must allow `refresh_token`; Authlib's `BearerToken.__call__(..., include_refresh_token=...)`). If the RFC-9068 generator doesn't emit a refresh token for the auth-code grant, check `AuthorizationCodeGrant` / generator interplay and adapt (you may need to ensure the grant requests it). Report what you found.
- [ ] **Step 4: PASS. Step 5: lint + commit** → `feat(oauth): issue + persist refresh tokens on auth-code flow`.

---

## Task 3: RefreshTokenGrant — rotation + revocation

**Files:** modify `oauth/server.py`; test add.

- [ ] **Step 1: failing test** (append) — exchange a refresh token for a new access+refresh, assert rotation (old revoked) and that a revoked refresh is rejected:
```python
@pytest.mark.asyncio
async def test_refresh_token_rotation_and_revocation(temp_context):
    import secrets, hashlib, base64
    from urllib.parse import urlparse, parse_qs
    await keystore.ensure_signing_key()
    await OAuthClient(
        client_id="cli_pub", client_secret_hash=None,
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"], scope="mcp", token_endpoint_auth_method="none",
    ).save()
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    a = StarletteOAuth2Request(
        method="POST", uri=f"{ISSUER}/oauth/authorize",
        query={"response_type": "code", "client_id": "cli_pub",
               "redirect_uri": "https://c.example/cb", "scope": "mcp",
               "code_challenge": challenge, "code_challenge_method": "S256"},
        form={}, headers={})
    r = await server.async_create_authorization_response(a, grant_user={"id": "u_1"})
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    t = StarletteOAuth2Request(
        method="POST", uri=f"{ISSUER}/oauth/token", query={},
        form={"grant_type": "authorization_code", "code": code,
              "redirect_uri": "https://c.example/cb", "client_id": "cli_pub",
              "code_verifier": verifier}, headers={})
    first = (await server.async_create_token_response(t)).body_json
    rt1 = first["refresh_token"]

    # exchange refresh -> new tokens
    t2 = StarletteOAuth2Request(
        method="POST", uri=f"{ISSUER}/oauth/token", query={},
        form={"grant_type": "refresh_token", "refresh_token": rt1, "client_id": "cli_pub"},
        headers={})
    second = (await server.async_create_token_response(t2)).body_json
    assert second.get("access_token")
    rt2 = second.get("refresh_token")
    assert rt2 and rt2 != rt1  # rotated

    # old refresh token now rejected
    t3 = StarletteOAuth2Request(
        method="POST", uri=f"{ISSUER}/oauth/token", query={},
        form={"grant_type": "refresh_token", "refresh_token": rt1, "client_id": "cli_pub"},
        headers={})
    resp3 = await server.async_create_token_response(t3)
    assert resp3.status_code in (400, 401)
    assert "access_token" not in (resp3.body_json or {})
```

- [ ] **Step 2: FAIL.**
- [ ] **Step 3: implement `JvSpatialRefreshTokenGrant(RefreshTokenGrant)`** in `server.py`:
  - `TOKEN_ENDPOINT_AUTH_METHODS = ["client_secret_basic", "client_secret_post", "none"]`; `INCLUDE_NEW_REFRESH_TOKEN = True`.
  - `authenticate_refresh_token(self, refresh_token)`: `rec = call_async(refresh_store.find_active, refresh_token)`; return a small credential object carrying `user_id`/`scope`/`client_id`/the raw token (Authlib passes this to `authenticate_user`/`revoke_old_credential`). If None → return None.
  - `authenticate_user(self, credential)`: return a `_GrantUser`-like object with `get_user_id()` → `credential.user_id`.
  - `revoke_old_credential(self, refresh_token)`: `call_async(refresh_store.revoke, <the OAuthRefreshToken record>)` — mark old inactive (rotation). (Map the credential back to the record; `find_active` then `revoke`, or carry the record on the credential.)
  - Register: `server.register_grant(JvSpatialRefreshTokenGrant)` in `build_authorization_server`.
  - The new refresh token from rotation is persisted by the existing `save_token` (Task 2) since `INCLUDE_NEW_REFRESH_TOKEN=True` puts it in the token dict.
  - RUNTIME-VALIDATION: confirm what object `authenticate_refresh_token` must return and how `revoke_old_credential` receives it on 1.7.2 (read `refresh_token.py`); adapt the credential object accordingly. Ensure the rotated refresh token's scope/resource carry over.
- [ ] **Step 4: PASS (rotation + old-token-rejected). Step 5: lint + commit** → `feat(oauth): refresh-token grant with rotation + revocation`.

---

## Task 4: scope∩permissions + token hardening (single-use atomic, nbf)

**Files:** modify `oauth/server.py`; test add.

- [ ] **Step 1: failing tests** (append):
```python
@pytest.mark.asyncio
async def test_scope_intersected_with_user_permissions(temp_context):
    import secrets, hashlib, base64
    from urllib.parse import urlparse, parse_qs
    import jwt as pyjwt
    await keystore.ensure_signing_key()
    await OAuthClient(
        client_id="cli_pub", client_secret_hash=None,
        redirect_uris=["https://c.example/cb"], grant_types=["authorization_code"],
        response_types=["code"], scope="mcp admin", token_endpoint_auth_method="none",
    ).save()
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    a = StarletteOAuth2Request(
        method="POST", uri=f"{ISSUER}/oauth/authorize",
        query={"response_type": "code", "client_id": "cli_pub",
               "redirect_uri": "https://c.example/cb", "scope": "mcp admin",
               "code_challenge": challenge, "code_challenge_method": "S256"},
        form={}, headers={})
    # user only has 'mcp' permission, not 'admin'
    r = await server.async_create_authorization_response(
        a, grant_user={"id": "u_1", "permissions": ["mcp"]})
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    t = StarletteOAuth2Request(
        method="POST", uri=f"{ISSUER}/oauth/token", query={},
        form={"grant_type": "authorization_code", "code": code,
              "redirect_uri": "https://c.example/cb", "client_id": "cli_pub",
              "code_verifier": verifier}, headers={})
    body = (await server.async_create_token_response(t)).body_json
    key = await keystore.get_active_signing_key()
    decoded = pyjwt.decode(body["access_token"], key.public_pem,
                           algorithms=["RS256"], audience=RESOURCE)
    granted = set(decoded.get("scope", "").split())
    assert "mcp" in granted and "admin" not in granted  # admin filtered out
    assert "nbf" in decoded  # hardening: nbf present
```

- [ ] **Step 2: FAIL** (admin not filtered / nbf absent).
- [ ] **Step 3: implement.** In `server.py`:
  - **scope∩permissions:** in `save_authorization_code`, compute granted scope = requested-allowed-scope ∩ user permissions. `grant_user` now may carry `permissions` (list). Helper `_intersect_scope(scope, permissions)`; store the intersected scope on the `AuthorizationCode`. (If `permissions` absent on grant_user — e.g. M1b-1 callers — fall back to the client-allowed scope unchanged, so existing tests stay green.) Document: M1b-3's route will populate `grant_user` permissions from the session user's `get_effective_permissions`.
  - **nbf:** override `get_extra_claims(self, client, grant_type, user, scope)` on `JvSpatialJWTTokenGenerator` to add `{"nbf": int(now)}` (and any spec claims). Verify RFC-9068 generator merges `get_extra_claims`.
  - **single-use atomic:** in `query_authorization_code`, consume-before-issue — flip `consumed=True` and save *before* returning the code object (so a concurrent second lookup sees it consumed). Keep `delete_authorization_code` as the post-hook (idempotent). Verify the existing single-use test still passes and add a note. (If Authlib calls `query_authorization_code` for read-only validation elsewhere, ensure consuming-on-query doesn't break the happy path — test it.)
- [ ] **Step 4: PASS** (scope filtered, nbf present) + existing happy-path/single-use tests green. **Step 5: lint + commit** → `fix(oauth): scope∩permissions + nbf claim + atomic single-use code`.

---

## Task 5: M1b-2 verification + security review

- [ ] **Step 1:** `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && python -m pytest tests/api/auth/oauth -q)` — all green (M1a + M1b-1 + M1b-2).
- [ ] **Step 2:** existing auth suite unaffected.
- [ ] **Step 3:** dispatch a security review of the refresh-rotation + scope-intersection diff (refresh replay after rotation, token-substitution, scope-escalation, hashed-at-rest).

---

## Self-Review Notes
- **Spec coverage:** addendum M1b-2 bullet (refresh rotation + scope∩perms) → Tasks 1–4; review-deferred minors (TOCTOU, nbf) → Task 4. Consent/session/route mounting deliberately deferred to M1b-3.
- **Deviation logged:** dedicated `OAuthRefreshToken` instead of reusing the shared session `RefreshToken` (isolation; carries client/scope/resource). Update the spec's §4 note when M1b-2 lands.
- **Type consistency:** `mint_refresh_token`/`find_active`/`revoke`, `OAuthRefreshToken`, `JvSpatialRefreshTokenGrant`, `_intersect_scope` named consistently across tasks/tests.

## Next
- **M1b-3** — DCR + revocation endpoint + RFC 8414 metadata + root `/.well-known/jwks.json` + consent page + `/authorize` session-user resolution + `oauth_router` registration + startup `ensure_signing_key` hook.
- **M1c** — Resource Server.
