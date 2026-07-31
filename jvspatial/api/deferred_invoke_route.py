"""Register POST {API_PREFIX}/_internal/deferred for Lambda Web Adapter pass-through."""

from __future__ import annotations

import hmac
import logging
from typing import Any, Dict, Optional

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

# LWA forwards non-HTTP (async self-invoke / EventBridge) payloads as POST from
# the local adapter process. Those requests cannot carry custom auth headers.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _deferred_invoke_disabled() -> bool:
    return env("JVSPATIAL_DEFERRED_INVOKE_DISABLED", default=False, parse=parse_bool)


def _client_host(request: Request) -> Optional[str]:
    client = request.client
    if client is None:
        return None
    host = (client.host or "").strip().lower()
    return host or None


def _is_loopback_client(request: Request) -> bool:
    """True when the peer is LWA / local adapter (not API Gateway / public HTTP)."""
    host = _client_host(request)
    return host in _LOOPBACK_HOSTS


def _deferred_invoke_secret_ok(request: Request) -> bool:
    """Authorize the internal deferred-invoke endpoint.

    Lambda Web Adapter self-invoke POSTs from loopback without auth headers, so
    loopback peers are always allowed. Non-loopback callers (Function URL /
    API Gateway) fail closed when ``JVSPATIAL_DEFERRED_INVOKE_SECRET`` is unset
    or empty (audit §4.16 / SPEC §15.2); when set, they must send the value in
    ``X-JVSPATIAL-Deferred-Authorize`` or ``Authorization: Bearer …``.

    Disable the route entirely via ``JVSPATIAL_DEFERRED_INVOKE_DISABLED=true``
    if you do not need it.
    """
    if _is_loopback_client(request):
        return True

    secret = env("JVSPATIAL_DEFERRED_INVOKE_SECRET") or ""
    if not secret:
        logger.warning(
            "Deferred-invoke route rejected: "
            "JVSPATIAL_DEFERRED_INVOKE_SECRET is unset and peer is not "
            "loopback (host=%r). Set a secret for public callers, or rely "
            "on LWA self-invoke from 127.0.0.1.",
            _client_host(request),
        )
        return False
    hdr = (request.headers.get("X-JVSPATIAL-Deferred-Authorize") or "").strip()
    auth = request.headers.get("Authorization") or ""
    bearer = ""
    if auth.lower().startswith("bearer "):
        bearer = auth[7:].strip()
    return hmac.compare_digest(hdr, secret) or hmac.compare_digest(bearer, secret)


def register_deferred_invoke_route(app: FastAPI) -> None:
    """Mount the internal deferred-invoke endpoint.

    Loopback callers (LWA pass-through) are always authorized. Non-loopback
    callers require ``JVSPATIAL_DEFERRED_INVOKE_SECRET`` via header
    ``X-JVSPATIAL-Deferred-Authorize`` or ``Authorization: Bearer …``.
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
