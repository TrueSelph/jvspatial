# M1b-1 — OAuth Core Authorization Server (Authlib + anyio bridge) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax. This phase is **security-critical** — run the security-review skill before merge.

**Goal:** Stand up the core OAuth 2.1 authorization-code+PKCE flow in jvspatial — a Starlette-bound Authlib `AuthorizationServer` whose sync hooks bridge to the M1a async `Object` storage via anyio, issuing RS256 (RFC 9068) access tokens — exercised end-to-end (`/authorize` consent-approve → code → `/token` exchange) in-process.

**Architecture:** Authlib core is synchronous; jvspatial storage is async-only. Route handlers run Authlib via `anyio.to_thread.run_sync`; Authlib's sync grant hooks reach async `Object` storage via `anyio.from_thread.run`. RS256 signing uses M1a `keys.py`. Builds strictly on M1a (`OAuthClient`, `AuthorizationCode`, `OAuthSigningKey`, `keys.ensure_signing_key`/`build_jwks`, `AuthConfig` OAuth fields).

**Tech Stack:** Authlib 1.x (`authlib.oauth2.rfc6749`/`rfc7636`/`rfc9068`/`jose`), anyio (via Starlette), PyJWT/cryptography (M1a), pytest+pytest-asyncio.

**Repo/branch:** `/Users/eldonmarks/Briefcase/dev/jv/jvspatial`, branch `feat/oauth2-service` (M1a committed; M1 spec + M1b addendum committed). venv: `.venv`.

**Pre-commit:** black/isort/flake8(+docstrings D-codes)/mypy/detect-secrets enforced — conform; no `--no-verify`.

> **RUNTIME-VALIDATION NOTE (read first):** Authlib's exact symbol surface varies across 1.x (see the M1b addendum "version traps"). The code below is grounded in research but each task's TDD loop is the source of truth — if an import path or method name differs on the installed Authlib, the implementer adjusts to the installed version and reports the delta (do NOT fabricate; verify with `python -c "import authlib; print(authlib.__version__)"` and read the installed source under `.venv/.../authlib/oauth2/`). Confirm Authlib is installed first: `pip show authlib` — if absent, add `authlib>=1.3` to `pyproject.toml` (RFC 9068 needs ≥1.3) as Task 0.

---

## File Structure
- `pyproject.toml` — *modify*: add `authlib>=1.3`.
- `jvspatial/api/auth/oauth/bridge.py` — *create*: anyio sync↔async helper.
- `jvspatial/api/auth/oauth/requests.py` — *create*: Starlette `OAuth2Request` wrapper + builder.
- `jvspatial/api/auth/oauth/client_adapter.py` — *create*: `ClientMixin` wrapper over `OAuthClient`.
- `jvspatial/api/auth/oauth/server.py` — *create*: `AuthorizationServer` subclass + grant + token generator + factory.
- `jvspatial/api/auth/oauth/routes.py` — *create*: `/oauth/authorize` + `/oauth/token` handlers (APIRouter).
- tests under `tests/api/auth/oauth/`.

(`oauth_router` registration into the app + startup key hook + `.well-known` routes are **M1b-3**, not this phase — M1b-1 drives the server in-process via tests.)

---

## Task 0: Ensure Authlib dependency

**Files:** `pyproject.toml`

- [ ] **Step 1:** `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && pip show authlib >/dev/null 2>&1 && echo PRESENT || echo MISSING)` + `python -c "import authlib,sys; print(getattr(authlib,'__version__','?'))" 2>/dev/null`.
- [ ] **Step 2:** If MISSING or version <1.3, add to `pyproject.toml` dependencies (below the `cryptography` line): `"authlib>=1.3",  # OAuth 2.1 authorization server (framework-agnostic core)`. Then `pip install -e .`.
- [ ] **Step 3:** Verify: `python -c "from authlib.oauth2.rfc6749 import AuthorizationServer, OAuth2Request; from authlib.oauth2.rfc7636 import CodeChallenge; from authlib.oauth2.rfc9068 import JWTBearerTokenGenerator; print('authlib OK')"`. If any import path differs, note the correct path from the installed source and record it for later tasks.
- [ ] **Step 4:** Commit (only `pyproject.toml`): `git -C /Users/eldonmarks/Briefcase/dev/jv/jvspatial commit -m "build(oauth): add authlib dependency" -- pyproject.toml` (commit the lockfile too only if one is tracked + changed).

---

## Task 1: anyio bridge + Starlette OAuth2Request wrapper

**Files:** create `jvspatial/api/auth/oauth/bridge.py`, `jvspatial/api/auth/oauth/requests.py`; test `tests/api/auth/oauth/test_oauth_bridge.py`.

- [ ] **Step 1: failing test** — `tests/api/auth/oauth/test_oauth_bridge.py`:
```python
"""anyio bridge: a sync function run in a worker thread can call back into
async code; and the Starlette OAuth2Request wrapper exposes args/form dicts."""

import anyio
import pytest

from jvspatial.api.auth.oauth.bridge import run_sync_with_async_bridge, call_async
from jvspatial.api.auth.oauth.requests import StarletteOAuth2Request


@pytest.mark.asyncio
async def test_bridge_runs_sync_that_calls_async():
    async def _async_double(x):
        return x * 2

    def _sync_work():
        # inside the worker thread, call back into async land
        return call_async(_async_double, 21)

    result = await run_sync_with_async_bridge(_sync_work)
    assert result == 42


def test_oauth2_request_wrapper_exposes_args_and_form():
    req = StarletteOAuth2Request(
        method="POST",
        uri="https://as.example/oauth/token?x=1",
        query={"x": "1"},
        form={"grant_type": "authorization_code", "code": "abc"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert req.args == {"x": "1"}
    assert req.form["grant_type"] == "authorization_code"
    assert req.form["code"] == "abc"
```

- [ ] **Step 2: run, verify FAIL** — `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && python -m pytest tests/api/auth/oauth/test_oauth_bridge.py -q)` → ImportError.

- [ ] **Step 3: implement bridge** — `jvspatial/api/auth/oauth/bridge.py`:
```python
"""Async/sync bridge for driving Authlib's synchronous OAuth core from async
route handlers while its hooks reach jvspatial's async ``Object`` storage.

Pattern: the route handler calls ``await run_sync_with_async_bridge(fn)`` which
runs ``fn`` (which internally calls Authlib's sync ``create_*_response``) in a
worker thread via ``anyio.to_thread.run_sync``. Inside that thread, Authlib's
sync grant hooks call ``call_async(coro_fn, *args)`` to execute async storage
coroutines back on the host event loop (blocking the worker until they resolve).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, TypeVar

import anyio
import anyio.from_thread
import anyio.to_thread

T = TypeVar("T")


async def run_sync_with_async_bridge(fn: Callable[..., T], *args: Any) -> T:
    """Run a blocking ``fn`` in a worker thread that may call ``call_async``."""
    return await anyio.to_thread.run_sync(fn, *args)


def call_async(coro_fn: Callable[..., Awaitable[T]], *args: Any) -> T:
    """From inside a worker thread (started by ``run_sync_with_async_bridge``),
    run an async coroutine on the host event loop and block for its result."""
    return anyio.from_thread.run(coro_fn, *args)
```

- [ ] **Step 4: implement request wrapper** — `jvspatial/api/auth/oauth/requests.py`:
```python
"""Starlette bindings for Authlib's framework-agnostic request objects.

We subclass ``OAuth2Request`` and override ``args`` (query params) and ``form``
(body params) to return plain dicts — the version-portable binding (avoids the
deprecated ``OAuth2Request(body=...)`` / ``request.data`` paths). ``build_*``
helpers construct these from a Starlette ``Request`` in the async handler before
handing off to the (threaded) sync Authlib call.
"""

from __future__ import annotations

from typing import Dict

from authlib.oauth2.rfc6749 import OAuth2Request

try:  # JSON request type moved across versions; tolerate absence
    from authlib.oauth2.rfc6749 import JsonRequest  # type: ignore
except Exception:  # pragma: no cover
    JsonRequest = None  # type: ignore


class StarletteOAuth2Request(OAuth2Request):
    """``OAuth2Request`` backed by pre-extracted Starlette query/form dicts."""

    def __init__(
        self,
        method: str,
        uri: str,
        query: Dict[str, str],
        form: Dict[str, str],
        headers: Dict[str, str],
    ) -> None:
        super().__init__(method, uri, headers=headers)
        self._query = dict(query or {})
        self._form = dict(form or {})

    @property
    def args(self) -> Dict[str, str]:
        return self._query

    @property
    def form(self) -> Dict[str, str]:
        return self._form


async def build_oauth2_request(request) -> StarletteOAuth2Request:
    """Build a ``StarletteOAuth2Request`` from a Starlette ``Request`` (async)."""
    form: Dict[str, str] = {}
    if request.method in ("POST", "PUT", "PATCH"):
        raw = await request.form()
        form = {k: v for k, v in raw.items()}
    return StarletteOAuth2Request(
        method=request.method,
        uri=str(request.url),
        query=dict(request.query_params),
        form=form,
        headers=dict(request.headers),
    )
```
RUNTIME-VALIDATION: if `OAuth2Request.__init__` on the installed version rejects this signature or `args`/`form` aren't the override points (read the installed `authlib/oauth2/rfc6749/requests.py`), adjust the override to match and report. The test pins the observable contract (`.args`/`.form`).

- [ ] **Step 5: run, verify PASS (2 tests).**
- [ ] **Step 6: lint/type + commit** `bridge.py requests.py test_oauth_bridge.py` → `feat(oauth): anyio sync/async bridge + Starlette OAuth2Request wrapper`.

---

## Task 2: ClientMixin adapter over OAuthClient

**Files:** create `jvspatial/api/auth/oauth/client_adapter.py`; test `tests/api/auth/oauth/test_oauth_client_adapter.py`.

- [ ] **Step 1: failing test**:
```python
"""ClientMixin adapter: wraps an OAuthClient so Authlib can validate it."""

from jvspatial.api.auth.oauth.client_adapter import OAuthClientAdapter
from jvspatial.api.auth.oauth.models import OAuthClient, hash_client_secret


def _client(**kw):
    base = dict(
        client_id="cli_1",
        client_secret_hash=None,
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp read",
        token_endpoint_auth_method="none",
    )
    base.update(kw)
    return OAuthClientAdapter(OAuthClient(**base))


def test_redirect_and_grant_checks():
    a = _client()
    assert a.get_client_id() == "cli_1"
    assert a.check_redirect_uri("https://c.example/cb") is True
    assert a.check_redirect_uri("https://evil.example/cb") is False
    assert a.check_grant_type("authorization_code") is True
    assert a.check_grant_type("client_credentials") is False
    assert a.check_response_type("code") is True
    assert a.get_default_redirect_uri() == "https://c.example/cb"


def test_public_client_auth_method_and_scope_filter():
    a = _client()
    assert a.check_endpoint_auth_method("none", "token") is True
    assert a.check_endpoint_auth_method("client_secret_basic", "token") is False
    # allowed scope filters requested down to the client's registered set
    assert set(a.get_allowed_scope("mcp write read").split()) == {"mcp", "read"}


def test_confidential_secret_check():
    a = _client(
        client_secret_hash=hash_client_secret("s3cret"),
        token_endpoint_auth_method="client_secret_post",
    )
    assert a.check_client_secret("s3cret") is True
    assert a.check_client_secret("nope") is False
    assert a.check_endpoint_auth_method("client_secret_post", "token") is True
```

- [ ] **Step 2: run, verify FAIL.**
- [ ] **Step 3: implement** — `jvspatial/api/auth/oauth/client_adapter.py`:
```python
"""Authlib ``ClientMixin`` adapter over the stored ``OAuthClient`` record."""

from __future__ import annotations

from authlib.oauth2.rfc6749 import ClientMixin

from jvspatial.api.auth.oauth.models import OAuthClient, verify_client_secret


class OAuthClientAdapter(ClientMixin):
    """Wrap an ``OAuthClient`` so Authlib can validate redirect/grant/scope/auth."""

    def __init__(self, client: OAuthClient) -> None:
        self.client = client

    def get_client_id(self) -> str:
        return self.client.client_id

    def get_default_redirect_uri(self):
        uris = self.client.redirect_uris or []
        return uris[0] if uris else None

    def get_allowed_scope(self, scope: str) -> str:
        if not scope:
            return ""
        allowed = set((self.client.scope or "").split())
        return " ".join(s for s in scope.split() if s in allowed)

    def check_redirect_uri(self, redirect_uri: str) -> bool:
        return redirect_uri in (self.client.redirect_uris or [])

    def check_client_secret(self, client_secret: str) -> bool:
        if not self.client.client_secret_hash:
            return False
        return verify_client_secret(client_secret, self.client.client_secret_hash)

    def check_endpoint_auth_method(self, method: str, endpoint: str) -> bool:
        # token endpoint: must match the client's registered method.
        return method == (self.client.token_endpoint_auth_method or "none")

    def check_response_type(self, response_type: str) -> bool:
        return response_type in (self.client.response_types or [])

    def check_grant_type(self, grant_type: str) -> bool:
        return grant_type in (self.client.grant_types or [])
```
RUNTIME-VALIDATION: confirm the `ClientMixin` method names on the installed Authlib (esp. `check_endpoint_auth_method(method, endpoint)` vs an older `check_token_endpoint_auth_method`). If the installed base declares additional abstract methods, implement them minimally and report.

- [ ] **Step 4: PASS. Step 5: lint + commit** → `feat(oauth): ClientMixin adapter over OAuthClient`.

---

## Task 3: AuthorizationServer + auth-code/PKCE grant + RS256 token generator

**Files:** create `jvspatial/api/auth/oauth/server.py`; test `tests/api/auth/oauth/test_oauth_server_flow.py`.

This is the security-critical core. The test drives the full PKCE authorization-code→token flow in-process (no HTTP), with a fake authenticated user, asserting a valid RS256 JWT comes out and that a tampered PKCE verifier is rejected.

- [ ] **Step 1: failing test** — `tests/api/auth/oauth/test_oauth_server_flow.py`:
```python
"""End-to-end (in-process) authorization_code + PKCE flow: build server,
register a public client + a user, run /authorize (approve) -> code, exchange
at /token -> RS256 JWT; tampered verifier is rejected."""

import base64
import hashlib
import secrets
import tempfile
import uuid

import jwt as pyjwt
import pytest

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.db.factory import create_database
from jvspatial.api.auth.oauth import keys as keystore
from jvspatial.api.auth.oauth.models import OAuthClient
from jvspatial.api.auth.oauth.requests import StarletteOAuth2Request
from jvspatial.api.auth.oauth.server import build_authorization_server


ISSUER = "https://as.example"
RESOURCE = "https://api.example/mcp"


@pytest.fixture
def temp_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        database = create_database("json", base_path=f"{tmpdir}/t_{uuid.uuid4().hex}")
        context = GraphContext(database=database)
        set_default_context(context)
        yield context


def _pkce():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


@pytest.mark.asyncio
async def test_authcode_pkce_happy_path_issues_rs256_jwt(temp_context):
    await keystore.ensure_signing_key()
    await OAuthClient(
        client_id="cli_pub",
        client_secret_hash=None,
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp",
        token_endpoint_auth_method="none",
    ).save()

    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    verifier, challenge = _pkce()

    # --- /authorize (consent approved) -> redirect with ?code= ---
    authorize_req = StarletteOAuth2Request(
        method="POST",
        uri=(
            f"{ISSUER}/oauth/authorize?response_type=code&client_id=cli_pub"
            f"&redirect_uri=https://c.example/cb&scope=mcp&state=xyz"
            f"&code_challenge={challenge}&code_challenge_method=S256"
        ),
        query={
            "response_type": "code",
            "client_id": "cli_pub",
            "redirect_uri": "https://c.example/cb",
            "scope": "mcp",
            "state": "xyz",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        form={},
        headers={},
    )
    resp = await server.async_create_authorization_response(
        authorize_req, grant_user={"id": "u_1"}
    )
    assert resp.status_code in (302, 303)
    location = resp.headers["location"]
    assert location.startswith("https://c.example/cb?")
    from urllib.parse import urlparse, parse_qs

    code = parse_qs(urlparse(location).query)["code"][0]
    assert code

    # --- /token (exchange) -> RS256 JWT ---
    token_req = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/token",
        query={},
        form={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://c.example/cb",
            "client_id": "cli_pub",
            "code_verifier": verifier,
        },
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    tok_resp = await server.async_create_token_response(token_req)
    assert tok_resp.status_code == 200
    body = tok_resp.body_json
    assert body["token_type"].lower() == "bearer"
    access = body["access_token"]

    # verify the JWT against the published JWKS public key
    key = await keystore.get_active_signing_key()
    decoded = pyjwt.decode(
        access, key.public_pem, algorithms=["RS256"], audience=RESOURCE,
        options={"verify_aud": True},
    )
    assert decoded["iss"] == ISSUER
    assert decoded["sub"] == "u_1"
    assert "mcp" in decoded.get("scope", "")


@pytest.mark.asyncio
async def test_tampered_pkce_verifier_rejected(temp_context):
    await keystore.ensure_signing_key()
    await OAuthClient(
        client_id="cli_pub",
        client_secret_hash=None,
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code"],
        response_types=["code"],
        scope="mcp",
        token_endpoint_auth_method="none",
    ).save()
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    _, challenge = _pkce()
    authorize_req = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/authorize",
        query={
            "response_type": "code", "client_id": "cli_pub",
            "redirect_uri": "https://c.example/cb", "scope": "mcp",
            "code_challenge": challenge, "code_challenge_method": "S256",
        },
        form={}, headers={},
    )
    resp = await server.async_create_authorization_response(
        authorize_req, grant_user={"id": "u_1"}
    )
    from urllib.parse import urlparse, parse_qs
    code = parse_qs(urlparse(resp.headers["location"]).query)["code"][0]
    token_req = StarletteOAuth2Request(
        method="POST", uri=f"{ISSUER}/oauth/token", query={},
        form={
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": "https://c.example/cb", "client_id": "cli_pub",
            "code_verifier": "WRONG-VERIFIER-VALUE-THAT-DOES-NOT-MATCH",
        },
        headers={},
    )
    tok_resp = await server.async_create_token_response(token_req)
    assert tok_resp.status_code in (400, 401)
    assert "access_token" not in (tok_resp.body_json or {})
```

- [ ] **Step 2: run, verify FAIL** (ImportError on `build_authorization_server`).

- [ ] **Step 3: implement** — `jvspatial/api/auth/oauth/server.py`. This wires: server subclass (binding methods + `query_client`/`save_token` bridged async), `AuthorizationCodeGrant` (hooks bridged to `AuthorizationCode` Object), `CodeChallenge(required=True)`, RFC 9068 RS256 token generator from `keys.py`, plus **async wrappers** `async_create_authorization_response` / `async_create_token_response` that run the sync Authlib calls through the anyio bridge and adapt the response. Build it against the installed Authlib (use the M1b addendum skeleton + research as the template). Key requirements the test pins:
  - `build_authorization_server(issuer, resource)` returns a server object.
  - `async_create_authorization_response(req, grant_user)` returns an object with `.status_code` and `.headers["location"]` (a redirect carrying `?code=`). `grant_user` is the authenticated user (dict/obj with `id`).
  - `async_create_token_response(req)` returns an object with `.status_code` and `.body_json` (parsed dict); success yields `access_token` (RS256 JWT, claims `iss/sub/aud/scope`), `token_type=bearer`.
  - Token generator signs with the **active** `OAuthSigningKey` private PEM + its `kid`, `aud`=`resource`, `iss`=`issuer`.
  - Grant hooks (`save_authorization_code`, `query_authorization_code`, `delete_authorization_code`, `authenticate_user`) persist/read `AuthorizationCode` via `call_async(...)`; PKCE `code_challenge`/`code_challenge_method` stored + verified.
  - `query_client` / `save_token` bridged to async storage.

  Implementer: write this module to satisfy the test, using `anyio.to_thread.run_sync(server.create_authorization_response, req, grant_user=...)` inside the `async_*` wrappers and `call_async` inside hooks. Convert Authlib's `handle_response(status, body, headers)` into a small response object exposing `.status_code`/`.headers`/`.body_json`. For RS256 via RFC 9068, subclass `JWTBearerTokenGenerator` with `get_jwks()` returning the active private JWK (build from `OAuthSigningKey.private_pem` + `kid`, `alg=RS256`) and `get_audiences()` returning `resource`. Register the auth-code grant with `[CodeChallenge(required=True)]`.

  RUNTIME-VALIDATION (expect iteration here): this is where Authlib's real API surface matters most. Read the installed `authlib/oauth2/rfc6749/grants/authorization_code.py`, `rfc7636/challenge.py`, `rfc9068/token.py` and adapt method names/signatures to the installed version. If `JWTBearerTokenGenerator` is absent (Authlib <1.3), STOP and report (Task 0 should have ensured ≥1.3). If the threaded `from_thread.run` portal errors under pytest's event loop, report the exact error — we may need to drive the bridge via `anyio.from_thread.BlockingPortal` explicitly; do not silently change the architecture.

- [ ] **Step 4: run, verify PASS (2 tests).** If the happy-path JWT decode fails on `aud`, confirm the generator sets `aud=resource`. If tampered-verifier returns 200, PKCE isn't enforced — fix the `CodeChallenge(required=True)` registration.
- [ ] **Step 5: security self-check** — confirm: code is single-use (second exchange of the same code fails); the JWT is RS256 (header alg) with a `kid`; no client secret or private PEM appears in any response body. Add a third test if quick.
- [ ] **Step 6: lint/type + commit** `server.py test_oauth_server_flow.py` → `feat(oauth): authorization-code+PKCE server issuing RS256 tokens (anyio-bridged)`.

---

## Task 4: M1b-1 verification

- [ ] **Step 1:** `(cd /Users/eldonmarks/Briefcase/dev/jv/jvspatial && python -m pytest tests/api/auth/oauth -q)` → all M1a + M1b-1 tests green.
- [ ] **Step 2:** existing auth suite unaffected: `python -m pytest tests/api/auth -q`.
- [ ] **Step 3:** import sanity: `python -c "from jvspatial.api.auth.oauth.server import build_authorization_server; print('M1b-1 OK')"`.

---

## Self-Review Notes
- **Spec coverage (M1b-1 slice):** addendum M1b-1 bullet (server adapter + bridge + client/grant adapters + RS256 token gen + /authorize+/token core) → Tasks 1–3; deps → Task 0. Refresh grant, consent UI/session, DCR, revocation, metadata, route-mounting + startup hook are **M1b-2/M1b-3** (not here).
- **Placeholder note:** Task 3's implementation is intentionally spec-by-contract (the test pins observable behavior) rather than fully pre-written, because the Authlib wiring must be validated against the installed version at runtime — pre-writing unverifiable internals would be a fabrication risk. All other tasks carry complete code. This is the one integration task where TDD-against-runtime is the correct discipline.
- **Type consistency:** `build_authorization_server(issuer, resource)`, `async_create_authorization_response(req, grant_user=...)`, `async_create_token_response(req)`, `run_sync_with_async_bridge`/`call_async`, `StarletteOAuth2Request(method,uri,query,form,headers)`, `OAuthClientAdapter(OAuthClient)` are named consistently across tasks/tests.

## Next
- **M1b-2** — RefreshTokenGrant (rotation) + consent page + session-user resolution + scope=requested∩permissions.
- **M1b-3** — DCR + revocation + RFC 8414 metadata + root-mounted `/.well-known/jwks.json` + `oauth_router` registration + startup `ensure_signing_key` hook.
