# M1b-3a — DCR + revocation + refresh reuse-detection + AS metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps. **Security-critical** — endpoints + reuse detection get a security review.

**Goal:** Add the in-process-testable OAuth endpoints + hardening: Dynamic Client Registration (RFC 7591), token Revocation (RFC 7009), refresh-token **reuse detection** (OAuth 2.1 family revocation — review finding I-3), and the RFC 8414 AS-metadata + JWKS document builders. HTTP route mounting + consent + session resolution + startup wiring are **M1b-3b** (planned after this lands).

**Architecture:** Extends `build_authorization_server` (M1b-1/2). DCR + revocation are Authlib endpoints registered on the server and invoked via async wrappers through the anyio bridge (same pattern as `async_create_token_response`). Reuse detection adds a `family_id` to `OAuthRefreshToken` carried across rotations. Metadata is a pure dict builder (validated by Authlib's RFC 8414 model).

**Tech Stack:** authlib 1.7.2 (`rfc7591.ClientRegistrationEndpoint`, `rfc7009.RevocationEndpoint`, `rfc8414.AuthorizationServerMetadata`), jvspatial Objects, anyio bridge. venv `.venv`. Pre-commit: black/isort/flake8(D-codes)/mypy/detect-secrets.

**Repo/branch:** jvspatial `feat/oauth2-service` (HEAD `23db9c5`; M1a+M1b-1+M1b-2 committed).

> **RUNTIME-VALIDATION:** verify endpoint method signatures against installed `.venv/.../authlib/oauth2/rfc7591/endpoint.py` + `rfc7009/revocation.py`; tests pin behavior. Confirmed available: DCR `ENDPOINT_NAME="client_registration"` (methods `authenticate_token`/`save_client`/`get_server_metadata`/`generate_client_id`/`generate_client_secret`); Revocation `ENDPOINT_NAME="revocation"` (`query_token`/`revoke_token`); `rfc8414.AuthorizationServerMetadata` present.

---

## Task 1: Refresh reuse-detection (I-3) — `family_id` + revoke-family-on-replay

**Files:** modify `oauth/models.py` (`OAuthRefreshToken` +`family_id`), `oauth/refresh_store.py` (+ family ops), `oauth/server.py` (rotation carries family; replay-of-revoked → family revoke). Test `tests/api/auth/oauth/test_oauth_refresh_reuse.py`.

- [ ] **Step 1: failing test**:
```python
"""OAuth 2.1 refresh reuse detection: replaying a rotated (revoked) refresh
token revokes the whole family, killing the attacker-or-victim live token."""

import tempfile, uuid, secrets, hashlib, base64
from urllib.parse import urlparse, parse_qs
import pytest

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.db.factory import create_database
from jvspatial.api.auth.oauth import keys as keystore, refresh_store
from jvspatial.api.auth.oauth.models import OAuthClient
from jvspatial.api.auth.oauth.requests import StarletteOAuth2Request
from jvspatial.api.auth.oauth.server import build_authorization_server

ISSUER = "https://as.example"
RESOURCE = "https://api.example/mcp"


@pytest.fixture
def temp_context():
    with tempfile.TemporaryDirectory() as d:
        set_default_context(GraphContext(database=create_database("json", base_path=f"{d}/t_{uuid.uuid4().hex}")))
        yield


async def _issue_first_refresh(server):
    await OAuthClient(
        client_id="cli_pub", client_secret_hash=None,
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"], scope="mcp", token_endpoint_auth_method="none",
    ).save()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    a = StarletteOAuth2Request(method="POST", uri=f"{ISSUER}/oauth/authorize",
        query={"response_type": "code", "client_id": "cli_pub", "redirect_uri": "https://c.example/cb",
               "scope": "mcp", "code_challenge": challenge, "code_challenge_method": "S256"}, form={}, headers={})
    r = await server.async_create_authorization_response(a, grant_user={"id": "u_1"})
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    t = StarletteOAuth2Request(method="POST", uri=f"{ISSUER}/oauth/token", query={},
        form={"grant_type": "authorization_code", "code": code, "redirect_uri": "https://c.example/cb",
              "client_id": "cli_pub", "code_verifier": verifier}, headers={})
    return (await server.async_create_token_response(t)).body_json["refresh_token"]


def _refresh_req(rt):
    return StarletteOAuth2Request(method="POST", uri=f"{ISSUER}/oauth/token", query={},
        form={"grant_type": "refresh_token", "refresh_token": rt, "client_id": "cli_pub"}, headers={})


@pytest.mark.asyncio
async def test_replay_of_rotated_token_revokes_family(temp_context):
    await keystore.ensure_signing_key()
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    rt1 = await _issue_first_refresh(server)
    rt2 = (await server.async_create_token_response(_refresh_req(rt1))).body_json["refresh_token"]
    assert rt2 and rt2 != rt1
    # attacker replays the rotated rt1 -> rejected AND family killed
    replay = await server.async_create_token_response(_refresh_req(rt1))
    assert replay.status_code in (400, 401)
    # rt2 (same family) is now dead too
    after = await server.async_create_token_response(_refresh_req(rt2))
    assert after.status_code in (400, 401)
    assert "access_token" not in (after.body_json or {})
```

- [ ] **Step 2: FAIL** (rt2 still works after rt1 replay).
- [ ] **Step 3: implement.**
  - `OAuthRefreshToken`: add `family_id: str = Field(default="", description="Rotation family; shared across rotations of one grant")`.
  - `refresh_store`: `mint_refresh_token(..., family_id)` stores it; add `find_any(token) -> Optional[OAuthRefreshToken]` (lookup by hash WITHOUT the `is_active` filter — so we can detect a presented-but-revoked token); add `revoke_family(family_id) -> int` (set is_active=False for all rows with that family_id).
  - `server.py` rotation: when minting the first refresh (auth-code flow `_persist_refresh`), generate a new `family_id` (uuid hex); on refresh rotation, the new token inherits the old token's `family_id`. (Thread `family_id` from the `_RefreshCredential.record.family_id` into the new mint — the `save_token` path needs access to it; carry it on the grant/credential or look it up.)
  - `JvSpatialRefreshTokenGrant.authenticate_refresh_token`: first try `find_active`. If None, try `find_any`; if a record exists but is `is_active=False` (a rotated/revoked token is being replayed) → `call_async(refresh_store.revoke_family, record.family_id)` and return None (reject). This converts replay-of-rotated into full-family invalidation.
  RUNTIME-VALIDATION: ensure the new-token mint in `save_token` can obtain the family_id of the token being refreshed (e.g. stash the current credential's family on the grant instance, or include it in the token dict). Verify by running.
- [ ] **Step 4: PASS** + existing refresh rotation test still green (normal rotation without replay keeps working). **Step 5: lint + commit** `models.py refresh_store.py server.py test_oauth_refresh_reuse.py` → `feat(oauth): refresh-token reuse detection (family revocation)`.

---

## Task 2: Dynamic Client Registration (RFC 7591)

**Files:** create `oauth/dcr.py` (`ClientRegistrationEndpoint` subclass); modify `oauth/server.py` (register endpoint + `async_register_client`); test `tests/api/auth/oauth/test_oauth_dcr.py`.

- [ ] **Step 1: failing test**:
```python
"""DCR: a client self-registers; an OAuthClient is persisted; public (PKCE)
client gets no secret."""

import tempfile, uuid
import pytest
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.db.factory import create_database
from jvspatial.api.auth.oauth.models import OAuthClient
from jvspatial.api.auth.oauth.requests import StarletteOAuth2Request
from jvspatial.api.auth.oauth.server import build_authorization_server

ISSUER = "https://as.example"
RESOURCE = "https://api.example/mcp"


@pytest.fixture
def temp_context():
    with tempfile.TemporaryDirectory() as d:
        set_default_context(GraphContext(database=create_database("json", base_path=f"{d}/t_{uuid.uuid4().hex}")))
        yield


@pytest.mark.asyncio
async def test_dcr_registers_public_client(temp_context):
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    req = StarletteOAuth2Request(
        method="POST", uri=f"{ISSUER}/oauth/register", query={},
        form={},  # DCR body is JSON, not form — see note
        headers={"content-type": "application/json"},
    )
    # JSON body carried explicitly for the registration endpoint:
    body = {
        "client_name": "Claude Code",
        "redirect_uris": ["https://c.example/cb"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "mcp",
    }
    resp = await server.async_register_client(req, body)
    assert resp.status_code in (200, 201)
    out = resp.body_json
    assert out["client_id"]
    assert out.get("token_endpoint_auth_method") == "none"
    # persisted
    rows = await OAuthClient.find({"context.client_id": out["client_id"]})
    assert len(rows) == 1
    assert rows[0].redirect_uris == ["https://c.example/cb"]
    # public client: no secret returned/stored
    assert not out.get("client_secret")
    assert rows[0].client_secret_hash is None
```

- [ ] **Step 2: FAIL.**
- [ ] **Step 3: implement** `oauth/dcr.py` — subclass `ClientRegistrationEndpoint`:
  - `authenticate_token(self, request)`: when `oauth_dcr_enabled` (open registration for MCP zero-config), return a sentinel truthy (open DCR). (If a deployment wants gated DCR, this is where an initial-access-token check goes — keep open for now, note it.)
  - `get_server_metadata(self)`: return the AS metadata dict (from Task 4's builder, or a minimal dict with `token_endpoint_auth_methods_supported` etc. so Authlib can validate requested metadata).
  - `save_client(self, client_info, client_metadata, request)`: build + persist an `OAuthClient` (`client_id=client_info["client_id"]`, secret hash only for confidential, redirect_uris/grant_types/response_types/scope/token_endpoint_auth_method from metadata) via `call_async`; return the persisted representation Authlib expects.
  - Register in `build_authorization_server`: `server.register_endpoint(JvSpatialClientRegistrationEndpoint)`.
  - Add `async def async_register_client(self, req, json_body)` to the server: set the JSON payload on the request (DCR uses `create_json_request`/`payload`), then `run_sync_with_async_bridge(partial(self.create_endpoint_response, "client_registration", req))`. RUNTIME-VALIDATION: confirm how the JSON body reaches the endpoint in 1.7.2 (the request needs its JSON payload populated — read `rfc7591/endpoint.py` `extract_client_metadata`/how it reads the body; you may need to populate `req.payload`/`req._body` from `json_body`). Adapt the wrapper so the endpoint sees the JSON metadata.
- [ ] **Step 4: PASS. Step 5: lint + commit** → `feat(oauth): dynamic client registration (RFC 7591)`.

---

## Task 3: Token Revocation (RFC 7009)

**Files:** create `oauth/revocation.py` (`RevocationEndpoint` subclass); modify `oauth/server.py` (register + `async_revoke_token`); test `tests/api/auth/oauth/test_oauth_revocation.py`.

- [ ] **Step 1: failing test** — revoke a refresh token → it can no longer be exchanged:
```python
"""RFC 7009 revocation: revoking a refresh token makes it unusable."""

import tempfile, uuid, secrets, hashlib, base64
from urllib.parse import urlparse, parse_qs
import pytest
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.db.factory import create_database
from jvspatial.api.auth.oauth import keys as keystore
from jvspatial.api.auth.oauth.models import OAuthClient
from jvspatial.api.auth.oauth.requests import StarletteOAuth2Request
from jvspatial.api.auth.oauth.server import build_authorization_server

ISSUER = "https://as.example"; RESOURCE = "https://api.example/mcp"


@pytest.fixture
def temp_context():
    with tempfile.TemporaryDirectory() as d:
        set_default_context(GraphContext(database=create_database("json", base_path=f"{d}/t_{uuid.uuid4().hex}")))
        yield


@pytest.mark.asyncio
async def test_revoke_refresh_token(temp_context):
    await keystore.ensure_signing_key()
    await OAuthClient(client_id="cli_pub", client_secret_hash=None,
        redirect_uris=["https://c.example/cb"], grant_types=["authorization_code", "refresh_token"],
        response_types=["code"], scope="mcp", token_endpoint_auth_method="none").save()
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    a = StarletteOAuth2Request(method="POST", uri=f"{ISSUER}/oauth/authorize",
        query={"response_type": "code", "client_id": "cli_pub", "redirect_uri": "https://c.example/cb",
               "scope": "mcp", "code_challenge": challenge, "code_challenge_method": "S256"}, form={}, headers={})
    code = parse_qs(urlparse((await server.async_create_authorization_response(a, grant_user={"id": "u_1"})).headers["location"]).query)["code"][0]
    t = StarletteOAuth2Request(method="POST", uri=f"{ISSUER}/oauth/token", query={},
        form={"grant_type": "authorization_code", "code": code, "redirect_uri": "https://c.example/cb",
              "client_id": "cli_pub", "code_verifier": verifier}, headers={})
    rt = (await server.async_create_token_response(t)).body_json["refresh_token"]

    rev = StarletteOAuth2Request(method="POST", uri=f"{ISSUER}/oauth/revoke", query={},
        form={"token": rt, "token_type_hint": "refresh_token", "client_id": "cli_pub"}, headers={})
    rev_resp = await server.async_revoke_token(rev)
    assert rev_resp.status_code == 200

    # revoked refresh can't be exchanged
    use = StarletteOAuth2Request(method="POST", uri=f"{ISSUER}/oauth/token", query={},
        form={"grant_type": "refresh_token", "refresh_token": rt, "client_id": "cli_pub"}, headers={})
    used = await server.async_create_token_response(use)
    assert used.status_code in (400, 401)
```

- [ ] **Step 2: FAIL.**
- [ ] **Step 3: implement** `oauth/revocation.py` — subclass `RevocationEndpoint`:
  - `query_token(self, token_string, token_type_hint)`: `call_async(refresh_store.find_any, token_string)` → return the OAuthRefreshToken record (or None). (Access tokens are stateless JWTs — revoking them needs a denylist, out of scope here; refresh revocation is the meaningful path. Note this.)
  - `revoke_token(self, token, request)`: `call_async(refresh_store.revoke, token)`.
  - Register in `build_authorization_server`: `server.register_endpoint(JvSpatialRevocationEndpoint)`; add `async def async_revoke_token(self, req)` → `run_sync_with_async_bridge(partial(self.create_endpoint_response, "revocation", req))`.
  RUNTIME-VALIDATION: confirm `query_token`/`revoke_token` signatures + how client auth on the revocation endpoint works for public clients (the test uses a public client; revocation may require client auth — verify `RevocationEndpoint.check_params`/client auth and ensure a public client can revoke its own token, or adjust the test/endpoint accordingly).
- [ ] **Step 4: PASS. Step 5: lint + commit** → `feat(oauth): token revocation endpoint (RFC 7009)`.

---

## Task 4: RFC 8414 AS-metadata + JWKS document builders

**Files:** create `oauth/metadata.py`; test `tests/api/auth/oauth/test_oauth_metadata.py`.

- [ ] **Step 1: failing test**:
```python
"""RFC 8414 AS metadata builder: required fields + validates."""

from jvspatial.api.auth.oauth.metadata import build_as_metadata


def test_metadata_required_fields():
    md = build_as_metadata(
        issuer="https://as.example", prefix="/oauth",
        scopes_supported=["mcp"],
    )
    assert md["issuer"] == "https://as.example"
    assert md["authorization_endpoint"].endswith("/oauth/authorize")
    assert md["token_endpoint"].endswith("/oauth/token")
    assert md["registration_endpoint"].endswith("/oauth/register")
    assert md["revocation_endpoint"].endswith("/oauth/revoke")
    assert md["jwks_uri"].endswith("/.well-known/jwks.json")
    assert "S256" in md["code_challenge_methods_supported"]
    assert "authorization_code" in md["grant_types_supported"]
    assert "refresh_token" in md["grant_types_supported"]
    assert "code" in md["response_types_supported"]
    # validates against Authlib's RFC 8414 model
    from authlib.oauth2.rfc8414 import AuthorizationServerMetadata
    AuthorizationServerMetadata(md).validate()
```

- [ ] **Step 2: FAIL.**
- [ ] **Step 3: implement** `oauth/metadata.py`:
```python
"""RFC 8414 Authorization Server Metadata builder (hand-served; Authlib only
validates, it does not serve)."""

from __future__ import annotations

from typing import Any, Dict, List


def build_as_metadata(*, issuer: str, prefix: str, scopes_supported: List[str]) -> Dict[str, Any]:
    """Build the RFC 8414 AS metadata document for this issuer."""
    base = issuer.rstrip("/")
    p = prefix.strip("/")
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/{p}/authorize",
        "token_endpoint": f"{base}/{p}/token",
        "registration_endpoint": f"{base}/{p}/register",
        "revocation_endpoint": f"{base}/{p}/revoke",
        "jwks_uri": f"{base}/.well-known/jwks.json",
        "scopes_supported": list(scopes_supported or []),
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": [
            "none", "client_secret_basic", "client_secret_post",
        ],
    }
```
VERIFY against Authlib's `AuthorizationServerMetadata.validate()` — if it requires/forbids a field, adjust (e.g. it may require `response_modes_supported` absent is fine). Report.
- [ ] **Step 4: PASS. Step 5: lint + commit** → `feat(oauth): RFC 8414 AS metadata builder`.

---

## Task 5: M1b-3a verification + security review
- [ ] `python -m pytest tests/api/auth/oauth -q` — all green.
- [ ] existing auth + a broad suite slice unaffected.
- [ ] security review of the DCR (open-registration abuse?), revocation (can a client revoke another's token?), and reuse-detection (family revocation correctness) diff.

## Self-Review Notes
- Covers addendum M1b-3 endpoints + review I-3. **Deferred to M1b-3b:** HTTP route mounting (oauth_router via AuthConfigurator, root `.well-known` routes), consent page + `/authorize` session-user resolution (the trust boundary — route MUST supply `grant_user.permissions`), startup `ensure_signing_key` hook, `oauth_signing_key_source` config. M1b-3b is integration-heavy (jvspatial server internals) and best validated by running the server — plan it after 3a.
- Names: `find_any`/`revoke_family`/`family_id`, `async_register_client`/`async_revoke_token`, `build_as_metadata` consistent across tasks/tests.

## Next: M1b-3b (wiring) → M1c (Resource Server) → M2 (Integral MCP endpoint) → M3 (UI).
