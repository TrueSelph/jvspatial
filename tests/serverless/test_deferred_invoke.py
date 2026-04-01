"""Tests for deferred-invoke registry and HTTP route."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jvspatial.api.constants import APIRoutes
from jvspatial.api.deferred_invoke_route import register_deferred_invoke_route
from jvspatial.serverless.deferred_invoke import (
    MalformedDeferredInvokeError,
    UnknownDeferredTaskError,
    clear_deferred_invoke_handlers,
    dispatch_deferred_invoke,
    normalize_deferred_envelope,
    register_deferred_invoke_handler,
)


@pytest.fixture(autouse=True)
def _clear_handlers():
    clear_deferred_invoke_handlers()
    yield
    clear_deferred_invoke_handlers()


def test_normalize_sqs_envelope_flattens_payload():
    out = normalize_deferred_envelope(
        {
            "task_type": "my.task",
            "payload": {"sender": "a", "n": 1},
            "reference": "ref-1",
        }
    )
    assert out["task_type"] == "my.task"
    assert out["sender"] == "a"
    assert out["n"] == 1
    assert out["reference"] == "ref-1"


def test_normalize_idempotent_for_lambda_flat_body():
    body = {"task_type": "t", "sender": "x"}
    assert normalize_deferred_envelope(body) is body


@pytest.mark.asyncio
async def test_dispatch_sqs_style_envelope():
    async def handler(event: dict) -> dict:
        return {"sender": event.get("sender")}

    register_deferred_invoke_handler("sqs.task", handler)
    out = await dispatch_deferred_invoke(
        {"task_type": "sqs.task", "payload": {"sender": "u1"}}
    )
    assert out == {"sender": "u1"}


@pytest.mark.asyncio
async def test_dispatch_registered_handler():
    async def handler(event: dict) -> dict:
        return {"echo": event.get("task_type"), "n": event.get("n")}

    register_deferred_invoke_handler("my.task", handler)
    out = await dispatch_deferred_invoke({"task_type": "my.task", "n": 3})
    assert out == {"echo": "my.task", "n": 3}


@pytest.mark.asyncio
async def test_dispatch_unknown_task_type():
    with pytest.raises(UnknownDeferredTaskError) as ei:
        await dispatch_deferred_invoke({"task_type": "missing.handler"})
    assert ei.value.task_type == "missing.handler"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"foo": 1}, {"task_type": ""}])
async def test_dispatch_malformed_task_type(body: dict):
    with pytest.raises(MalformedDeferredInvokeError):
        await dispatch_deferred_invoke(body)


def test_deferred_invoke_http_route():
    app = FastAPI()

    async def handler(event: dict) -> dict:
        return {"ok": True, "sender": event.get("sender")}

    register_deferred_invoke_handler("app.whatsapp.media_batch", handler)
    register_deferred_invoke_route(app)
    register_deferred_invoke_route(app)

    path = APIRoutes.deferred_invoke_full_path()
    client = TestClient(app)
    r = client.post(
        path,
        json={
            "task_type": "app.whatsapp.media_batch",
            "sender": "u1",
            "media_batch_window": 1.5,
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "sender": "u1"}


def test_deferred_invoke_http_unknown_returns_404():
    app = FastAPI()
    register_deferred_invoke_route(app)
    client = TestClient(app)
    path = APIRoutes.deferred_invoke_full_path()
    r = client.post(path, json={"task_type": "no.such.task"})
    assert r.status_code == 404
    assert "Unknown task_type" in r.json()["detail"]


def test_deferred_invoke_http_secret_header(monkeypatch):
    monkeypatch.setenv("JVSPATIAL_DEFERRED_INVOKE_SECRET", "test-secret-value")
    app = FastAPI()

    async def handler(event: dict) -> dict:
        return {"ok": True}

    register_deferred_invoke_handler("secret.task", handler)
    register_deferred_invoke_route(app)
    path = APIRoutes.deferred_invoke_full_path()
    client = TestClient(app)
    r = client.post(path, json={"task_type": "secret.task"})
    assert r.status_code == 401
    r2 = client.post(
        path,
        json={"task_type": "secret.task"},
        headers={"X-JVSPATIAL-Deferred-Authorize": "test-secret-value"},
    )
    assert r2.status_code == 200
    r3 = client.post(
        path,
        json={"task_type": "secret.task"},
        headers={"Authorization": "Bearer test-secret-value"},
    )
    assert r3.status_code == 200


def test_deferred_invoke_route_skipped_when_disabled(monkeypatch):
    monkeypatch.setenv("JVSPATIAL_DEFERRED_INVOKE_DISABLED", "true")
    app = FastAPI()
    register_deferred_invoke_route(app)
    client = TestClient(app)
    path = APIRoutes.deferred_invoke_full_path()
    r = client.post(path, json={"task_type": "any"})
    assert r.status_code == 404


def test_top_level_jvspatial_reexports_deferred_helpers():
    from jvspatial import (
        dispatch_deferred_invoke,
        normalize_deferred_envelope,
        register_deferred_invoke_handler,
    )

    assert callable(register_deferred_invoke_handler)
    assert callable(dispatch_deferred_invoke)
    assert callable(normalize_deferred_envelope)
