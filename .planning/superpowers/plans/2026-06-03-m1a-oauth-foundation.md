# M1a — OAuth Foundation (storage + config + key store) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the non-protocol foundation of jvspatial's OAuth 2.1 service — storage `Object` models, RS256 signing-key store + JWKS, and `AuthConfig` fields — so M1b (Authlib AS) and M1c (RS) build on verified ground.

**Architecture:** New `jvspatial/api/auth/oauth/` subpackage. Pure jvspatial `Object` persistence + `cryptography`/PyJWT for RS256 keys. No Authlib, no HTTP routes yet — every unit is independently testable with the existing `temp_context` json-DB fixture. All OAuth config is off by default; existing auth is untouched.

**Tech Stack:** Python 3.11, jvspatial `Object` ORM, `cryptography` (new dep), PyJWT (existing; RS256 needs `cryptography`), pytest + pytest-asyncio.

**Repo/branch:** `/Users/eldonmarks/Briefcase/dev/jv/jvspatial`, branch `feat/oauth2-service` (already created; M1 spec committed there).

---

## File Structure

- `pyproject.toml` — *modify*: add `cryptography` dependency.
- `jvspatial/api/auth/oauth/__init__.py` — *create*: subpackage marker + exports.
- `jvspatial/api/auth/oauth/models.py` — *create*: `OAuthClient`, `AuthorizationCode`, `OAuthSigningKey` (+ secret hash/verify helpers).
- `jvspatial/api/auth/oauth/keys.py` — *create*: RS256 key store (generate/persist/load/JWKS).
- `jvspatial/api/config_groups.py` — *modify*: add OAuth fields to `AuthConfig`.
- `tests/api/auth/oauth/test_oauth_models.py` — *create*.
- `tests/api/auth/oauth/test_oauth_keys.py` — *create*.
- `tests/api/auth/oauth/test_oauth_authconfig.py` — *create*.

Convention note: the existing `tests/core/test_entity_crud_and_cascade.py` shows the persistence test harness — a `temp_context` fixture that builds a `GraphContext` over a json DB in a tempdir; creating the context registers it as the default, so `Object.save/get/find` work. Reuse that fixture verbatim in each test module.

---

## Task 1: Add the `cryptography` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Confirm it's missing**

Run: `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && grep -n "cryptography" pyproject.toml || echo MISSING)`
Expected: `MISSING`.

- [ ] **Step 2: Add the dependency**

In `pyproject.toml`, the `dependencies` array contains `"PyJWT>=2.0.0",  # JWT token handling for authentication`. Add directly below it:

```toml
    "cryptography>=42.0.0",  # RS256 keypair generation + PyJWT RS256 signing/verification (OAuth)
```

- [ ] **Step 3: Install + verify RS256 is usable**

Run: `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && pip install -e . >/dev/null 2>&1; python -c "import cryptography, jwt; from cryptography.hazmat.primitives.asymmetric import rsa; print('crypto', cryptography.__version__)")`
Expected: prints `crypto <version>` with no ImportError.

- [ ] **Step 4: Commit**

```bash
git -C /Users/eldonmarks/Briefcase/dev/jv/jvspatial add pyproject.toml
git -C /Users/eldonmarks/Briefcase/dev/jv/jvspatial commit -m "build(oauth): add cryptography dependency for RS256"
```

---

## Task 2: OAuth storage models — `OAuthClient` + `AuthorizationCode`

**Files:**
- Create: `jvspatial/api/auth/oauth/__init__.py`
- Create: `jvspatial/api/auth/oauth/models.py`
- Test: `tests/api/auth/oauth/test_oauth_models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/auth/oauth/test_oauth_models.py`:

```python
"""OAuth storage models: persistence + secret hashing. Uses the json-DB temp
context fixture (mirrors tests/core/test_entity_crud_and_cascade.py)."""

import tempfile
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from jvspatial.core.context import GraphContext
from jvspatial.db.factory import create_database
from jvspatial.api.auth.oauth.models import (
    AuthorizationCode,
    OAuthClient,
    hash_client_secret,
    verify_client_secret,
)


@pytest.fixture
def temp_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        unique_path = f"{tmpdir}/test_{uuid.uuid4().hex}"
        database = create_database("json", base_path=unique_path)
        context = GraphContext(database=database)
        yield context


def test_secret_hash_roundtrip():
    secret = "s3cr3t-value"
    hashed = hash_client_secret(secret)
    assert hashed != secret
    assert verify_client_secret(secret, hashed) is True
    assert verify_client_secret("wrong", hashed) is False


@pytest.mark.asyncio
async def test_oauth_client_persist_and_find_by_client_id(temp_context):
    client = OAuthClient(
        client_id="cli_abc123",
        client_secret_hash=hash_client_secret("topsecret"),
        client_name="Claude Code",
        redirect_uris=["http://localhost:8765/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp",
        token_endpoint_auth_method="none",
    )
    await client.save()
    assert client.id is not None

    found = await OAuthClient.find({"context.client_id": "cli_abc123"})
    assert len(found) == 1
    assert found[0].client_name == "Claude Code"
    assert found[0].redirect_uris == ["http://localhost:8765/callback"]
    assert found[0].token_endpoint_auth_method == "none"


@pytest.mark.asyncio
async def test_authorization_code_persist_and_consume(temp_context):
    code = AuthorizationCode(
        code_hash="deadbeef",
        client_id="cli_abc123",
        user_id="u_1",
        redirect_uri="http://localhost:8765/callback",
        code_challenge="abc",
        code_challenge_method="S256",
        scope="mcp",
        resource="https://integral.example.com/api/mcp",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    await code.save()

    found = await AuthorizationCode.find({"context.code_hash": "deadbeef"})
    assert len(found) == 1
    assert found[0].consumed is False
    assert found[0].code_challenge_method == "S256"

    found[0].consumed = True
    await found[0].save()
    reread = await AuthorizationCode.find({"context.code_hash": "deadbeef"})
    assert reread[0].consumed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && python -m pytest tests/api/auth/oauth/test_oauth_models.py -q)`
Expected: FAIL — `ModuleNotFoundError: No module named 'jvspatial.api.auth.oauth'`.

- [ ] **Step 3: Create the subpackage + models**

Create `jvspatial/api/auth/oauth/__init__.py`:

```python
"""jvspatial OAuth 2.1 service (opt-in). Storage models + key store (M1a);
Authlib authorization server (M1b) and resource server (M1c) build on these."""
```

Create `jvspatial/api/auth/oauth/models.py`:

```python
"""OAuth 2.1 storage entities, stored as jvspatial Objects (no graph edges),
mirroring the APIKey/RefreshToken pattern in jvspatial/api/auth/models.py.

Secrets are never stored in plaintext: client secrets are SHA-256 hashed
(256-bit secrets => SHA-256 is appropriate; constant-time compare on verify),
matching the APIKey hashing rationale.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import Field

from jvspatial.core.entities import Object


def hash_client_secret(secret: str) -> str:
    """SHA-256 hash of a client secret for storage."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_client_secret(secret: str, hashed: str) -> bool:
    """Constant-time verify of a client secret against its stored hash."""
    return hmac.compare_digest(hash_client_secret(secret), hashed)


class OAuthClient(Object):
    """A registered OAuth client (RFC 7591 dynamic registration target).

    Public clients (PKCE, no secret) use ``token_endpoint_auth_method="none"``
    and have ``client_secret_hash=None``. Confidential clients store a hash.
    """

    client_id: str = Field(..., description="Public client identifier")
    client_secret_hash: Optional[str] = Field(
        default=None, description="SHA-256 hash of client secret (confidential only)"
    )
    client_name: str = Field(default="", description="Human-readable client name")
    redirect_uris: List[str] = Field(
        default_factory=list, description="Registered redirect URIs (exact match)"
    )
    grant_types: List[str] = Field(
        default_factory=lambda: ["authorization_code", "refresh_token"],
        description="Allowed grant types",
    )
    response_types: List[str] = Field(
        default_factory=lambda: ["code"], description="Allowed response types"
    )
    scope: str = Field(default="", description="Space-delimited allowed scopes")
    token_endpoint_auth_method: str = Field(
        default="none", description="none (public/PKCE) | client_secret_post | basic"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Registration timestamp",
    )


class AuthorizationCode(Object):
    """A single-use OAuth authorization code (PKCE). Short-lived; consumed on
    token exchange."""

    code_hash: str = Field(..., description="SHA-256 hash of the authorization code")
    client_id: str = Field(..., description="Owning client_id")
    user_id: str = Field(..., description="Authenticated resource-owner user id")
    redirect_uri: str = Field(..., description="Redirect URI used in the request")
    code_challenge: str = Field(..., description="PKCE code challenge")
    code_challenge_method: str = Field(default="S256", description="PKCE method (S256)")
    scope: str = Field(default="", description="Granted scope (space-delimited)")
    resource: Optional[str] = Field(
        default=None, description="RFC 8707 resource indicator (audience)"
    )
    expires_at: datetime = Field(..., description="Expiry (short, <= 10 min)")
    consumed: bool = Field(default=False, description="True once exchanged")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && python -m pytest tests/api/auth/oauth/test_oauth_models.py -q)`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git -C /Users/eldonmarks/Briefcase/dev/jv/jvspatial add jvspatial/api/auth/oauth/__init__.py jvspatial/api/auth/oauth/models.py tests/api/auth/oauth/test_oauth_models.py
git -C /Users/eldonmarks/Briefcase/dev/jv/jvspatial commit -m "feat(oauth): OAuthClient + AuthorizationCode storage models"
```

---

## Task 3: RS256 signing-key store + JWKS (`OAuthSigningKey` + `keys.py`)

**Files:**
- Modify: `jvspatial/api/auth/oauth/models.py` (add `OAuthSigningKey`)
- Create: `jvspatial/api/auth/oauth/keys.py`
- Test: `tests/api/auth/oauth/test_oauth_keys.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/auth/oauth/test_oauth_keys.py`:

```python
"""RS256 signing-key store: generate/persist/load + JWKS shape + sign/verify
roundtrip with PyJWT."""

import tempfile
import uuid

import jwt
import pytest

from jvspatial.core.context import GraphContext
from jvspatial.db.factory import create_database
from jvspatial.api.auth.oauth import keys as keystore


@pytest.fixture
def temp_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        unique_path = f"{tmpdir}/test_{uuid.uuid4().hex}"
        database = create_database("json", base_path=unique_path)
        context = GraphContext(database=database)
        yield context


@pytest.mark.asyncio
async def test_ensure_signing_key_idempotent(temp_context):
    k1 = await keystore.ensure_signing_key()
    assert k1.kid
    assert "BEGIN PUBLIC KEY" in k1.public_pem
    assert "BEGIN PRIVATE KEY" in k1.private_pem
    assert k1.algorithm == "RS256"
    # Second call returns the same active key, does not generate a new one.
    k2 = await keystore.ensure_signing_key()
    assert k2.kid == k1.kid


@pytest.mark.asyncio
async def test_jwks_contains_active_key(temp_context):
    key = await keystore.ensure_signing_key()
    jwks = await keystore.build_jwks()
    assert "keys" in jwks and len(jwks["keys"]) >= 1
    entry = next(j for j in jwks["keys"] if j["kid"] == key.kid)
    assert entry["kty"] == "RSA"
    assert entry["alg"] == "RS256"
    assert entry["use"] == "sig"
    assert "n" in entry and "e" in entry
    assert "d" not in entry  # never expose the private exponent


@pytest.mark.asyncio
async def test_sign_and_verify_roundtrip(temp_context):
    key = await keystore.ensure_signing_key()
    token = jwt.encode(
        {"sub": "u_1", "aud": "https://r.example/api/mcp"},
        key.private_pem,
        algorithm="RS256",
        headers={"kid": key.kid},
    )
    # Verify using the public PEM (what the JWKS publishes).
    decoded = jwt.decode(
        token, key.public_pem, algorithms=["RS256"], audience="https://r.example/api/mcp"
    )
    assert decoded["sub"] == "u_1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && python -m pytest tests/api/auth/oauth/test_oauth_keys.py -q)`
Expected: FAIL — `ImportError`/`AttributeError` (`keys` module / functions absent).

- [ ] **Step 3: Add the `OAuthSigningKey` model**

Append to `jvspatial/api/auth/oauth/models.py`:

```python
class OAuthSigningKey(Object):
    """A persisted RS256 signing keypair. ``active`` keys sign new tokens;
    inactive-but-recent keys remain in JWKS for the verification window
    (rotation). Private PEM stored as-is here; production deployments should
    wrap it (env/KMS) — see plan assumptions."""

    kid: str = Field(..., description="Key ID (JWKS 'kid')")
    public_pem: str = Field(..., description="PEM-encoded public key")
    private_pem: str = Field(..., description="PEM-encoded private key")
    algorithm: str = Field(default="RS256", description="Signing algorithm")
    active: bool = Field(default=True, description="Whether this key signs new tokens")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )
```

- [ ] **Step 4: Create the key store**

Create `jvspatial/api/auth/oauth/keys.py`:

```python
"""RS256 signing-key store for the OAuth AS.

Generates/persists RSA keypairs as ``OAuthSigningKey`` Objects, exposes the
active signing key, and builds the JWKS (public keys only) the AS publishes at
``/.well-known/jwks.json``.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import jwt  # PyJWT
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from jvspatial.api.auth.oauth.models import OAuthSigningKey


def _generate_rsa_pem_pair() -> tuple[str, str]:
    """Return (private_pem, public_pem) for a fresh RSA-2048 keypair."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


async def generate_signing_key() -> OAuthSigningKey:
    """Create, persist, and return a new active RS256 signing key."""
    private_pem, public_pem = _generate_rsa_pem_pair()
    key = OAuthSigningKey(
        kid=uuid.uuid4().hex,
        public_pem=public_pem,
        private_pem=private_pem,
        algorithm="RS256",
        active=True,
    )
    await key.save()
    return key


async def get_active_signing_key() -> Optional[OAuthSigningKey]:
    """Return the active signing key (newest if several), or None."""
    active = await OAuthSigningKey.find({"context.active": True})
    if not active:
        return None
    return sorted(active, key=lambda k: k.created_at, reverse=True)[0]


async def ensure_signing_key() -> OAuthSigningKey:
    """Return the active signing key, generating one if none exists."""
    existing = await get_active_signing_key()
    if existing is not None:
        return existing
    return await generate_signing_key()


async def _jwks_keys() -> List[OAuthSigningKey]:
    """All keys whose public half should appear in JWKS (active + recent).

    M1a: include every persisted key so tokens signed by a just-rotated key
    still verify. Rotation pruning (drop keys older than the max token TTL)
    lands with rotation in M1b.
    """
    return await OAuthSigningKey.find({})


async def build_jwks() -> Dict[str, Any]:
    """Build the JWKS document (public keys only) for the AS metadata."""
    keys = await _jwks_keys()
    jwks_keys: List[Dict[str, Any]] = []
    for k in keys:
        # PyJWT renders an RSA public key to a JWK (n/e/kty); add kid/use/alg.
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
            k.public_pem, as_dict=True
        )
        jwk.update({"kid": k.kid, "use": "sig", "alg": k.algorithm})
        jwk.pop("d", None)  # defensive: never publish a private exponent
        jwks_keys.append(jwk)
    return {"keys": jwks_keys}
```

Note: `RSAAlgorithm.to_jwk(..., as_dict=True)` returns a dict (PyJWT ≥ 2.x). It accepts a PEM string or key object; passing the public PEM yields a public JWK with `kty/n/e`.

- [ ] **Step 5: Run test to verify it passes**

Run: `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && python -m pytest tests/api/auth/oauth/test_oauth_keys.py -q)`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git -C /Users/eldonmarks/Briefcase/dev/jv/jvspatial add jvspatial/api/auth/oauth/models.py jvspatial/api/auth/oauth/keys.py tests/api/auth/oauth/test_oauth_keys.py
git -C /Users/eldonmarks/Briefcase/dev/jv/jvspatial commit -m "feat(oauth): RS256 signing-key store + JWKS"
```

---

## Task 4: `AuthConfig` OAuth fields (off by default)

**Files:**
- Modify: `jvspatial/api/config_groups.py` (`AuthConfig`)
- Test: `tests/api/auth/oauth/test_oauth_authconfig.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/auth/oauth/test_oauth_authconfig.py`:

```python
"""AuthConfig OAuth fields: present, correctly defaulted (all off/empty), and
overridable."""

from jvspatial.api.config_groups import AuthConfig


def test_oauth_defaults_off():
    cfg = AuthConfig()
    assert cfg.oauth_enabled is False
    assert cfg.oauth_prefix == "/oauth"
    assert cfg.oauth_supported_scopes == []
    assert cfg.oauth_dcr_enabled is True
    assert cfg.oauth_access_token_ttl_minutes == 60
    assert cfg.oauth_code_ttl_seconds == 300
    assert cfg.accept_oauth_bearer is False
    assert cfg.oauth_issuer_url == ""


def test_oauth_fields_overridable():
    cfg = AuthConfig(
        oauth_enabled=True,
        oauth_issuer_url="https://integral.example.com",
        oauth_supported_scopes=["mcp"],
        accept_oauth_bearer=True,
    )
    assert cfg.oauth_enabled is True
    assert cfg.oauth_issuer_url == "https://integral.example.com"
    assert cfg.oauth_supported_scopes == ["mcp"]
    assert cfg.accept_oauth_bearer is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && python -m pytest tests/api/auth/oauth/test_oauth_authconfig.py -q)`
Expected: FAIL — `AttributeError`/validation error (`oauth_enabled` not a field).

- [ ] **Step 3: Add the fields**

In `jvspatial/api/config_groups.py`, inside the `AuthConfig(BaseModel)` class (after the existing RBAC/registration fields, before any `model_config`/validators), add:

```python
    # --- OAuth 2.1 service (opt-in; see api/auth/oauth/). All off/empty by
    # default so existing apps are unaffected. ---
    oauth_enabled: bool = Field(
        default=False, description="Enable the OAuth 2.1 authorization server"
    )
    oauth_issuer_url: str = Field(
        default="", description="OAuth issuer URL (https origin) for token iss + metadata"
    )
    oauth_prefix: str = Field(
        default="/oauth", description="Route prefix for OAuth endpoints"
    )
    oauth_supported_scopes: List[str] = Field(
        default_factory=list, description="Advertised OAuth scopes (RBAC permission strings)"
    )
    oauth_dcr_enabled: bool = Field(
        default=True, description="Enable Dynamic Client Registration (RFC 7591)"
    )
    oauth_access_token_ttl_minutes: int = Field(
        default=60, description="OAuth access token lifetime (minutes)"
    )
    oauth_code_ttl_seconds: int = Field(
        default=300, description="Authorization code lifetime (seconds)"
    )
    accept_oauth_bearer: bool = Field(
        default=False,
        description="Resource-server: accept OAuth access tokens on auth=True endpoints",
    )
```

If `List` is not already imported at the top of `config_groups.py`, add `List` to the `from typing import ...` line. (Verify the existing import line first; `AuthConfig` already uses `Dict`/`List` for `role_permission_mapping`/`exempt_paths`, so `List` is almost certainly already imported — do not duplicate.)

- [ ] **Step 4: Run test to verify it passes**

Run: `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && python -m pytest tests/api/auth/oauth/test_oauth_authconfig.py -q)`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git -C /Users/eldonmarks/Briefcase/dev/jv/jvspatial add jvspatial/api/config_groups.py tests/api/auth/oauth/test_oauth_authconfig.py
git -C /Users/eldonmarks/Briefcase/dev/jv/jvspatial commit -m "feat(oauth): AuthConfig OAuth fields (off by default)"
```

---

## Task 5: M1a verification

**Files:** none (verification only)

- [ ] **Step 1: Full OAuth foundation suite green**

Run: `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && python -m pytest tests/api/auth/oauth -q)`
Expected: PASS (8 tests: 3 models + 3 keys + 2 config).

- [ ] **Step 2: No regression in existing auth suite**

Run: `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && python -m pytest tests/api/auth -q)`
Expected: PASS / unchanged from baseline (the new fields default off; no existing behavior touched). If pre-existing failures unrelated to OAuth exist, confirm they also fail on `dev` before this branch.

- [ ] **Step 3: Import-surface sanity**

Run: `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && python -c "from jvspatial.api.auth.oauth.models import OAuthClient, AuthorizationCode, OAuthSigningKey; from jvspatial.api.auth.oauth import keys; from jvspatial.api.config_groups import AuthConfig; print('M1a imports OK')")`
Expected: `M1a imports OK`.

---

## Self-Review Notes

- **Spec coverage (M1a slice):** spec §4 storage models → Tasks 2–3; spec §5 key store → Task 3; spec §8 config → Task 4; `cryptography`/RS256 prerequisite → Task 1. Spec §2 (AS), §3 (RS), §6 (scopes wiring), §7 (consent) are deliberately M1b/M1c — not in this plan.
- **Placeholder scan:** every code/command step is concrete; no TBD.
- **Type consistency:** `hash_client_secret`/`verify_client_secret`, `OAuthClient`/`AuthorizationCode`/`OAuthSigningKey`, `ensure_signing_key`/`get_active_signing_key`/`generate_signing_key`/`build_jwks` are named identically across tasks/tests. Model field names used in tests match the model definitions.
- **Plan-time assumption to verify at Task 3:** `jwt.algorithms.RSAAlgorithm.to_jwk(pem, as_dict=True)` returns a dict on the installed PyJWT. If the installed PyJWT predates `as_dict`, fall back to `json.loads(RSAAlgorithm.to_jwk(pem))` — adjust in-step if the test reveals it.

---

## Next (after M1a lands)
- **M1b** — Authlib `AuthorizationServer`, grants bound to these models, `/authorize`+consent / `/token` / `/register` / `/revoke` + AS-metadata + JWKS routes (uses `keys.build_jwks`).
- **M1c** — Resource Server (`ResourceProtector` + JWKS verifier), PRM, 401, `accept_oauth_bearer` middleware integration.
