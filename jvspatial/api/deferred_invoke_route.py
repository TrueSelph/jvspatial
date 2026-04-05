"""Register POST {API_PREFIX}/_internal/deferred for Lambda Web Adapter pass-through."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request

from jvspatial.api.constants import APIRoutes
from jvspatial.env import env, parse_bool
from jvspatial.serverless.deferred_invoke import (
    MalformedDeferredInvokeError,
    UnknownDeferredTaskError,
    dispatch_deferred_invoke,
)

logger = logging.getLogger(__name__)

_DEFERRED_INVOKE_REGISTERED_ATTR = "_jvspatial_deferred_invoke_route_registered"


def _deferred_invoke_disabled() -> bool:
    return env("JVSPATIAL_DEFERRED_INVOKE_DISABLED", default=False, parse=parse_bool)


def _deferred_invoke_secret_ok(request: Request) -> bool:
    secret = env("JVSPATIAL_DEFERRED_INVOKE_SECRET") or ""
    if not secret:
        return True
    hdr = (request.headers.get("X-JVSPATIAL-Deferred-Authorize") or "").strip()
    auth = request.headers.get("Authorization") or ""
    bearer = ""
    if auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()
    return hdr == secret or bearer == secret


def register_deferred_invoke_route(app: FastAPI) -> None:
    """Mount the internal deferred-invoke endpoint.

    When ``JVSPATIAL_DEFERRED_INVOKE_SECRET`` is set, requests must send the same
    value in header ``X-JVSPATIAL-Deferred-Authorize`` or ``Authorization: Bearer …``.
    Set ``JVSPATIAL_DEFERRED_INVOKE_DISABLED=true`` to skip registering the route.
    """

    if _deferred_invoke_disabled():
        logger.info(
            "Deferred invoke route not registered (JVSPATIAL_DEFERRED_INVOKE_DISABLED)"
        )
        return

    if getattr(app, _DEFERRED_INVOKE_REGISTERED_ATTR, False):
        return

    path = APIRoutes.deferred_invoke_full_path()

    @app.post(
        path,
        response_model=None,
        tags=["internal"],
        include_in_schema=False,
        name="jvspatial_deferred_invoke",
    )
    async def jvspatial_deferred_invoke(request: Request) -> Dict[str, Any]:
        if not _deferred_invoke_secret_ok(request):
            raise HTTPException(status_code=401, detail="Deferred invoke unauthorized")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from None
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object")
        try:
            return await dispatch_deferred_invoke(body)
        except MalformedDeferredInvokeError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        except UnknownDeferredTaskError as e:
            raise HTTPException(
                status_code=404, detail=f"Unknown task_type: {e.task_type!r}"
            ) from None

    setattr(app, _DEFERRED_INVOKE_REGISTERED_ATTR, True)
    logger.debug("Registered deferred invoke route: POST %s", path)
