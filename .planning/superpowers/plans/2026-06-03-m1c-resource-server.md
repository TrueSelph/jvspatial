# M1c — Resource Server (JWKS verifier + PRM + accept_oauth_bearer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps. **Security-critical** — gets a security review.

**Goal:** Complete M1 by adding the Resource-Server side: verify OAuth RS256 access tokens against the local JWKS (audience-bound), serve RFC 9728 Protected Resource Metadata + the 401 `WWW-Authenticate` discovery header, and let `@endpoint(auth=True)` optionally accept OAuth access tokens (`accept_oauth_bearer`) alongside session JWTs.

**Architecture:** AS and RS are the same jvspatial process, so the verifier reads the local public JWKS (`keys.build_jwks`). A pure async verifier (PyJWT) validates `iss`/`aud`/`exp`/signature and returns claims. The auth middleware gains an OAuth-bearer fallback: when session-JWT validation fails and `accept_oauth_bearer` is on, verify as an OAuth token (audience-checked) and set `request.state.user` from `sub` + `scope`. PRM + 401 are plain routes/helpers.

**Tech Stack:** PyJWT (RS256 verify against JWKS), jvspatial auth middleware, the M1b oauth subpackage. venv `.venv`. Pre-commit: black/isort/flake8(D-codes)/mypy/detect-secrets.

**Repo/branch:** jvspatial `feat/oauth2-service` (HEAD `dc9879d`; M1a+M1b complete).

> Confirmed: `auth_middleware._authenticate_jwt` (~line 301) does `user = await auth_service.validate_token(token)` (~343) → the fallback hook. `keys.build_jwks()` returns the public JWKS; `keys.get_active_signing_key()` + all `OAuthSigningKey` rows give public PEMs. AS issued tokens with `iss=issuer`, `aud=resource` where `resource==oauth_issuer_url`.

---

## Task 1: OAuth access-token verifier (`oauth/resource.py`)

**Files:** create `jvspatial/api/auth/oauth/resource.py`; test `tests/api/auth/oauth/test_oauth_resource_verify.py`.

- [ ] **Step 1: failing test**:
```python
"""RS verifier: accepts a valid AS-issued token; rejects wrong-aud/expired/bad-sig/wrong-iss."""

import tempfile, uuid, time
import pytest
import jwt as pyjwt
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.db.factory import create_database
from jvspatial.api.auth.oauth import keys as keystore
from jvspatial.api.auth.oauth.resource import verify_oauth_access_token

ISSUER = "https://as.example"; RESOURCE = "https://as.example"


@pytest.fixture
def temp_context():
    with tempfile.TemporaryDirectory() as d:
        set_default_context(GraphContext(database=create_database("json", base_path=f"{d}/t_{uuid.uuid4().hex}")))
        yield


async def _mint(claims):
    key = await keystore.ensure_signing_key()
    base = {"iss": ISSUER, "aud": RESOURCE, "sub": "u_1", "scope": "mcp",
            "iat": int(time.time()), "exp": int(time.time()) + 300, "jti": uuid.uuid4().hex}
    base.update(claims)
    return pyjwt.encode(base, key.private_pem, algorithm="RS256", headers={"kid": key.kid})


@pytest.mark.asyncio
async def test_valid_token_accepted(temp_context):
    tok = await _mint({})
    claims = await verify_oauth_access_token(tok, issuer=ISSUER, resource=RESOURCE)
    assert claims is not None and claims["sub"] == "u_1" and "mcp" in claims["scope"]


@pytest.mark.asyncio
async def test_wrong_audience_rejected(temp_context):
    tok = await _mint({"aud": "https://other.example"})
    assert await verify_oauth_access_token(tok, issuer=ISSUER, resource=RESOURCE) is None


@pytest.mark.asyncio
async def test_expired_rejected(temp_context):
    tok = await _mint({"exp": int(time.time()) - 10})
    assert await verify_oauth_access_token(tok, issuer=ISSUER, resource=RESOURCE) is None


@pytest.mark.asyncio
async def test_wrong_issuer_rejected(temp_context):
    tok = await _mint({"iss": "https://evil.example"})
    assert await verify_oauth_access_token(tok, issuer=ISSUER, resource=RESOURCE) is None


@pytest.mark.asyncio
async def test_bad_signature_rejected(temp_context):
    await keystore.ensure_signing_key()
    # token signed by a DIFFERENT key
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    pk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = pk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    import time as _t
    forged = pyjwt.encode({"iss": ISSUER, "aud": RESOURCE, "sub": "u_x", "scope": "mcp",
                           "exp": int(_t.time()) + 300}, pem, algorithm="RS256", headers={"kid": "nope"})
    assert await verify_oauth_access_token(forged, issuer=ISSUER, resource=RESOURCE) is None
```

- [ ] **Step 2: FAIL.**
- [ ] **Step 3: implement `jvspatial/api/auth/oauth/resource.py`**:
```python
"""OAuth Resource-Server token verification (RS256 against the local JWKS).

AS and RS are the same jvspatial process; the verifier reads the public signing
keys via the keystore and validates iss/aud/exp/signature. Best-effort: returns
the claims dict on success, ``None`` on any failure (never raises to callers).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import jwt  # PyJWT
from cryptography.hazmat.primitives import serialization

from jvspatial.api.auth.oauth.models import OAuthSigningKey

logger = logging.getLogger(__name__)


async def _public_pem_for_kid(kid: Optional[str]) -> Optional[str]:
    rows = await OAuthSigningKey.find({})  # all keys (active + rotated, for verify window)
    for k in rows:
        if kid is None or k.kid == kid:
            return k.public_pem
    return None


async def verify_oauth_access_token(
    token: str, *, issuer: str, resource: str
) -> Optional[Dict[str, Any]]:
    """Verify an OAuth RS256 access token; return claims or ``None``.

    Checks signature (JWKS by ``kid``), ``iss`` == issuer, ``aud`` contains
    ``resource`` (audience binding — confused-deputy mitigation), and ``exp``.
    """
    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        return None
    pub = await _public_pem_for_kid(header.get("kid"))
    if not pub:
        return None
    try:
        claims = jwt.decode(
            token, pub, algorithms=["RS256"], audience=resource, issuer=issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except Exception as exc:
        logger.debug("oauth access token rejected: %s", exc)
        return None
    return claims
```
RUNTIME-VALIDATION: confirm PyJWT `decode(audience=...)` accepts a scalar `aud` claim equal to `resource` (our tokens set `aud` to the resource string). If the AS sets `aud` as a list, PyJWT still matches membership — fine. Verify the bad-signature case truly fails (kid mismatch → no key → None, OR wrong-key decode → InvalidSignatureError → None).

- [ ] **Step 4: PASS (5 tests). Step 5: lint + commit** `resource.py` + test → `feat(oauth): resource-server access-token verifier`.

---

## Task 2: PRM (RFC 9728) + 401 helper

**Files:** modify `jvspatial/api/auth/oauth/metadata.py` (add `build_prm`); modify `jvspatial/api/auth/oauth/routes.py` (well_known route + helper); test `tests/api/auth/oauth/test_oauth_prm_http.py`.

- [ ] **Step 1: failing test** — boot Server(oauth_enabled), GET `/.well-known/oauth-protected-resource`:
```python
import tempfile, uuid
from fastapi.testclient import TestClient
from jvspatial.api.server import Server


def _app(tmp):
    s = Server(title="t", db_type="json", db_path=f"{tmp}/db_{uuid.uuid4().hex}",
               auth=dict(auth_enabled=True, jwt_secret="x" * 40, oauth_enabled=True,
                         oauth_issuer_url="https://as.example", oauth_supported_scopes=["mcp"]))
    return s.get_app()


def test_prm_served():
    with tempfile.TemporaryDirectory() as tmp:
        r = TestClient(_app(tmp)).get("/.well-known/oauth-protected-resource")
        assert r.status_code == 200
        b = r.json()
        assert b["resource"] == "https://as.example"
        assert "https://as.example" in b["authorization_servers"]
        assert b["jwks_uri"] == "https://as.example/.well-known/jwks.json"
        assert b.get("bearer_methods_supported") == ["header"]
```
- [ ] **Step 2: FAIL.**
- [ ] **Step 3: implement** `build_prm(*, resource, issuer, scopes_supported)` in `metadata.py`:
```python
def build_prm(*, resource: str, issuer: str, scopes_supported: List[str]) -> Dict[str, Any]:
    """RFC 9728 Protected Resource Metadata for ``resource``."""
    base = issuer.rstrip("/")
    return {
        "resource": resource.rstrip("/"),
        "authorization_servers": [base],
        "jwks_uri": f"{base}/.well-known/jwks.json",
        "bearer_methods_supported": ["header"],
        "scopes_supported": list(scopes_supported or []),
    }
```
   Add `GET /.well-known/oauth-protected-resource` to `well_known_router` in `routes.py` → `build_prm(resource=auth_config.oauth_issuer_url, issuer=auth_config.oauth_issuer_url, scopes_supported=auth_config.oauth_supported_scopes)`. Add a `www_authenticate_header(issuer)` helper returning `f'Bearer resource_metadata="{issuer}/.well-known/oauth-protected-resource"'` for later 401 use.
- [ ] **Step 4: PASS. Step 5: lint + commit** → `feat(oauth): protected-resource metadata (RFC 9728) + 401 helper`.

---

## Task 3: `accept_oauth_bearer` middleware integration

**Files:** modify `jvspatial/api/components/auth_middleware.py` (OAuth fallback in `_authenticate_jwt`); test `tests/api/auth/oauth/test_oauth_bearer_middleware.py`.

- [ ] **Step 1: failing test** — boot Server with `accept_oauth_bearer=True`; mint an OAuth access token (via the AS / keystore); call an `auth=True` endpoint with it as Bearer → authorized (principal from sub+scope). And: session-JWT path still works; an OAuth token with wrong aud → 401; with `accept_oauth_bearer=False` an OAuth token → 401.
   (Use an existing `@endpoint(auth=True)` route, e.g. `/api/auth/me`, or a trivial protected route the test registers. Mint the token by booting the AS + driving authorize→token, OR directly via keystore-signing like Task 1's `_mint` with the right iss/aud. The simplest: sign a token with iss=issuer, aud=issuer, sub=<an existing user id>, scope=<perm> using the active key, then hit a protected route. Confirm `request.state.user` is populated.)
- [ ] **Step 2: FAIL.**
- [ ] **Step 3: implement.** In `auth_middleware._authenticate_jwt`, after `user = await auth_service.validate_token(token)` returns falsy, and when the auth config has `accept_oauth_bearer` true:
  - `from jvspatial.api.auth.oauth.resource import verify_oauth_access_token`
  - `claims = await verify_oauth_access_token(token, issuer=cfg.oauth_issuer_url, resource=cfg.oauth_issuer_url)`
  - on success, build a principal compatible with what downstream expects from `request.state.user` (mirror `UserResponse` shape or whatever `validate_token` returns): `id=claims["sub"]`, `permissions=claims.get("scope","").split()`, `roles=[]`, `email=""`, `is_active=True`. Set `request.state.user = principal` and return it.
  - Access the auth config: the middleware already has it (find how `_authenticate_jwt` reads config — it has `auth_service`/config; use `cfg.accept_oauth_bearer`/`cfg.oauth_issuer_url`). If not directly available, thread it.
  - Session-JWT path unchanged; when `accept_oauth_bearer` false, skip the fallback entirely.
  RUNTIME-VALIDATION: confirm the downstream principal contract (what `request.state.user` must expose — `.id`/`.permissions`? a `UserResponse`? a dict?). Match `validate_token`'s return type so RBAC/`@endpoint` permission checks work. Verify a protected route accepts the OAuth token.
- [ ] **Step 4: PASS (oauth token authorizes; session unchanged; wrong-aud/disabled → 401). Step 5: lint + commit** → `feat(oauth): accept OAuth bearer tokens on protected endpoints (accept_oauth_bearer)`.

---

## Task 4: M1c verification + security review
- [ ] `python -m pytest tests/api/auth -q` + a broad slice green.
- [ ] security review: audience binding (no token-for-other-resource accepted), no `alg=none`/key-confusion, the synthesized principal can't escalate (permissions come only from the token's `scope`, which the AS already intersected), session path untouched, disabled-by-default.

## Self-Review Notes
- Completes spec §3 (Resource Server). After M1c, **M1 is complete** (reusable OAuth AS+RS, off by default) → ready to merge to jvspatial `dev`.
- Deferred (tracked): per-request RFC-8707 resource (aud fixed = issuer); access-token `jti` denylist; multi-worker CAS atomicity.
- Names: `verify_oauth_access_token`, `build_prm`, `www_authenticate_header` consistent.

## Next: M1 merge → **M2** (Integral MCP endpoint, integral repo) → **M3** (Agents UI).
