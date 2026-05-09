"""AppBuilder — JVSPATIAL_DOCS_DISABLED unpublish behavior.

Verifies that the single env knob fully removes the documentation surface
(`/docs`, `/redoc`, `/openapi.json`, `/docs/oauth2-redirect`) without
otherwise affecting the application.
"""

from __future__ import annotations

from typing import Optional

import pytest
from fastapi.testclient import TestClient

from jvspatial.api.components.app_builder import AppBuilder
from jvspatial.api.config import ServerConfig


def _build_client(config: Optional[ServerConfig] = None) -> TestClient:
    """Construct an AppBuilder-built FastAPI app + add a probe route."""
    cfg = config or ServerConfig()
    app = AppBuilder(cfg).create_app()

    @app.get("/__probe")
    def _probe() -> dict:
        return {"ok": True}

    return TestClient(app)


def test_docs_published_by_default() -> None:
    """Without the env flag, /docs and /openapi.json render."""
    client = _build_client()
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200


@pytest.mark.parametrize("flag", ["1", "true", "True", "yes", "on"])
def test_docs_unpublished_via_env_flag(monkeypatch, flag: str) -> None:
    """`JVSPATIAL_DOCS_DISABLED=<truthy>` returns 404 on every doc surface."""
    monkeypatch.setenv("JVSPATIAL_DOCS_DISABLED", flag)
    client = _build_client()
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    # Swagger's OAuth2 redirect helper is also stripped.
    assert client.get("/docs/oauth2-redirect").status_code == 404


def test_app_routes_unaffected_when_docs_disabled(monkeypatch) -> None:
    """Disabling docs leaves application routes alone."""
    monkeypatch.setenv("JVSPATIAL_DOCS_DISABLED", "1")
    client = _build_client()
    r = client.get("/__probe")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.mark.parametrize("flag", ["", "0", "false", "no", "off", "garbage"])
def test_falsey_or_unrelated_values_keep_docs_published(monkeypatch, flag: str) -> None:
    """Only the documented truthy values disable docs."""
    if flag:
        monkeypatch.setenv("JVSPATIAL_DOCS_DISABLED", flag)
    else:
        monkeypatch.delenv("JVSPATIAL_DOCS_DISABLED", raising=False)
    client = _build_client()
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_disabled_state_strips_openapi_schema_endpoint(monkeypatch) -> None:
    """`/openapi.json` is the metadata leak that matters most in prod —
    confirm it is gone (not just inaccessible)."""
    monkeypatch.setenv("JVSPATIAL_DOCS_DISABLED", "1")
    cfg = ServerConfig()
    app = AppBuilder(cfg).create_app()

    # FastAPI exposes the openapi mount via app.openapi_url; should be None.
    assert app.openapi_url is None
    # And the spec generator returns nothing usable when openapi_url is off.
    schema = app.openapi()
    # FastAPI still synthesizes a schema in-memory, but the route is not
    # registered — the public surface is what matters and we already
    # asserted 404 above. Sanity-check the schema is a dict (no crash).
    assert isinstance(schema, dict)
