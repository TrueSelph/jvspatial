"""SecurityHeadersMiddleware — per-path CSP behavior.

Production unpublish lives elsewhere: `JVSPATIAL_DOCS_DISABLED=1` in
`AppBuilder.create_app` removes the routes outright, so this middleware
only ever sees app routes. When docs ARE published (dev/staging) the
relaxed `_DOCS_CSP` permits the Swagger UI / ReDoc CDN bundles.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jvspatial.api.middleware.manager import (
    _DEFAULT_CSP,
    _DOCS_CSP,
    SecurityHeadersMiddleware,
)


def _build_client() -> TestClient:
    """Spin a minimal FastAPI app + a docs sub-path probe."""
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/health")
    def _health() -> dict:
        return {"ok": True}

    @app.get("/docs/extra")
    def _docs_subpath() -> dict:
        return {"docs": True}

    return TestClient(app)


def test_app_route_gets_strict_csp() -> None:
    """Application routes receive the locked-down default CSP."""
    client = _build_client()
    r = client.get("/health")
    assert r.headers["content-security-policy"] == _DEFAULT_CSP


def test_docs_route_gets_relaxed_csp() -> None:
    """`/docs` (FastAPI default) gets the CDN-permitting CSP so Swagger UI loads."""
    app = FastAPI()  # FastAPI auto-mounts /docs and /openapi.json
    app.add_middleware(SecurityHeadersMiddleware)
    client = TestClient(app)

    r = client.get("/docs")
    assert r.status_code == 200
    assert r.headers["content-security-policy"] == _DOCS_CSP

    r2 = client.get("/openapi.json")
    assert r2.status_code == 200
    assert r2.headers["content-security-policy"] == _DOCS_CSP


def test_docs_subpath_also_relaxed() -> None:
    """Docs path matching includes sub-paths (e.g. /docs/oauth2-redirect)."""
    client = _build_client()
    r = client.get("/docs/extra")
    assert r.headers["content-security-policy"] == _DOCS_CSP


def test_constant_security_headers_always_present() -> None:
    """X-Content-Type-Options + X-Frame-Options ride along on every response."""
    client = _build_client()
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


def test_hsts_off_by_default() -> None:
    client = _build_client()
    r = client.get("/health")
    assert "strict-transport-security" not in {k.lower() for k in r.headers}


def test_hsts_on_when_constructor_flag_enabled() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=True)

    @app.get("/x")
    def _x() -> dict:
        return {"ok": True}

    client = TestClient(app)
    r = client.get("/x")
    assert "max-age=31536000" in r.headers["strict-transport-security"]
