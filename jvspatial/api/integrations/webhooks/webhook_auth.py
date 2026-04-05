"""Webhook API key authentication and cache.

Extracted from webhook middleware for separation of concerns.
Handles API key validation, caching, and IP/endpoint restrictions.
"""

import asyncio
import hashlib
import logging
import time
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# API key validation cache: (expiry_timestamp, api_key_entity)
# TTL 300s, max 500 entries. Reduces DB round-trips for repeated webhook calls.
_API_KEY_CACHE: Dict[str, Tuple[float, Any]] = {}
_API_KEY_CACHE_TTL = 300.0
_API_KEY_CACHE_MAX_SIZE = 500
_API_KEY_VALIDATE_TIMEOUT = 10.0


def _api_key_cache_cleanup() -> None:
    """Remove expired entries from API key cache."""
    now = time.time()
    expired = [k for k, (exp, _) in _API_KEY_CACHE.items() if exp <= now]
    for k in expired:
        del _API_KEY_CACHE[k]


async def authenticate_webhook_api_key(
    request: Request,
    auth_mode: str,
    webhook_config: Optional[Dict[str, Any]] = None,
    server: Optional[Any] = None,
) -> None:
    """Authenticate webhook request using API key.

    Supports:
    - Query parameter: ?api_key=sk_live_...
    - Header: X-API-Key: sk_live_...
    - Path parameter: /webhook/{api_key}/trigger

    Args:
        request: FastAPI request object
        auth_mode: Authentication mode ("api_key" or "api_key_path")
        webhook_config: Webhook configuration dictionary
        server: Server instance for config defaults

    Raises:
        HTTPException: If authentication fails
    """
    from jvspatial.api.auth.api_key_service import APIKeyService
    from jvspatial.core.context import GraphContext
    from jvspatial.db import get_prime_database

    api_key = None
    source = None

    # Get configuration with defaults
    api_key_header = "x-api-key"  # pragma: allowlist secret
    api_key_query_param = "api_key"  # pragma: allowlist secret
    require_https = True

    if webhook_config:
        api_key_header = webhook_config.get("api_key_header", api_key_header)
        api_key_query_param = webhook_config.get(
            "api_key_query_param", api_key_query_param
        )
        require_https = webhook_config.get(
            "api_key_query_param_require_https", require_https
        )

    # Try to get server config for defaults
    if server:
        server_config = getattr(server, "config", None)
        if server_config:
            api_key_header = (
                server_config.webhook.webhook_api_key_header or api_key_header
            )
            api_key_query_param = (
                server_config.webhook.webhook_api_key_query_param or api_key_query_param
            )
            require_https = server_config.webhook.webhook_api_key_require_https

    if auth_mode == "api_key_path":
        path = request.url.path
        path_parts = [p for p in path.split("/") if p]
        try:
            webhook_idx = None
            for i, part in enumerate(path_parts):
                if part == "webhook":
                    webhook_idx = i
                    break
            if webhook_idx is not None and webhook_idx + 1 < len(path_parts):
                api_key = path_parts[webhook_idx + 1]
                source = "path"
        except (ValueError, IndexError):
            pass

    if not api_key and auth_mode == "api_key":
        api_key = request.query_params.get(api_key_query_param)
        if api_key:
            source = "query_param"
            if require_https:
                is_https = (
                    request.url.scheme == "https"
                    or request.headers.get("x-forwarded-proto") == "https"
                    or request.headers.get("x-forwarded-ssl") == "on"
                )
                if not is_https:
                    logger.warning(
                        f"Webhook API key authentication via query parameter rejected: "
                        f"HTTPS required but request was {request.url.scheme}"
                    )
                    raise HTTPException(
                        status_code=400,
                        detail="HTTPS required for query parameter authentication",
                    )

    if not api_key:
        api_key = request.headers.get(api_key_header)
        if api_key:
            source = "header"

    if not api_key:
        raise HTTPException(
            status_code=401, detail="API key required for webhook authentication"
        )

    try:
        cache_key = hashlib.sha256(api_key.encode()).hexdigest()
        now = time.time()
        cache_hit = False
        if cache_key in _API_KEY_CACHE:
            cached_expiry, cached_entity = _API_KEY_CACHE[cache_key]
            if cached_expiry > now and cached_entity is not None:
                api_key_entity = cached_entity
                cache_hit = True
                logger.debug(f"Webhook API key cache hit: key_id={cached_entity.id}")
            else:
                api_key_entity = None
                del _API_KEY_CACHE[cache_key]
        else:
            api_key_entity = None

        prime_ctx = None
        service = None
        if api_key_entity is None:
            prime_ctx = GraphContext(database=get_prime_database())
            service = APIKeyService(prime_ctx)
            try:
                api_key_entity = await asyncio.wait_for(
                    service.validate_key(api_key),
                    timeout=_API_KEY_VALIDATE_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Webhook API key validation timed out (DB slow or unavailable)"
                )
                raise HTTPException(
                    status_code=503,
                    detail="Service temporarily unavailable",
                )
            if api_key_entity:
                if len(_API_KEY_CACHE) >= _API_KEY_CACHE_MAX_SIZE:
                    _api_key_cache_cleanup()
                _API_KEY_CACHE[cache_key] = (
                    now + _API_KEY_CACHE_TTL,
                    api_key_entity,
                )

        if not api_key_entity:
            raise HTTPException(status_code=401, detail="Invalid or expired API key")

        client_ip = request.client.host if request.client else None
        if (
            api_key_entity.allowed_ips
            and client_ip
            and client_ip not in api_key_entity.allowed_ips
        ):
            logger.debug(
                f"Webhook API key {api_key_entity.id} rejected: IP {client_ip} not in whitelist"
            )
            raise HTTPException(status_code=403, detail="IP address not allowed")

        if api_key_entity.allowed_endpoints:
            request_path = request.url.path

            def _endpoint_allowed(ep: str) -> bool:
                if ep.endswith("*"):
                    prefix = ep[:-1]
                    return request_path.startswith(prefix)
                return request_path.startswith(ep)

            if not any(
                _endpoint_allowed(ep) for ep in api_key_entity.allowed_endpoints
            ):
                logger.debug(
                    f"Webhook API key {api_key_entity.id} rejected: endpoint {request_path} not in whitelist"
                )
                raise HTTPException(
                    status_code=403, detail="Endpoint not allowed for this API key"
                )

        request.state.user = {
            "user_id": api_key_entity.user_id,
            "api_key_id": api_key_entity.id,
            "permissions": api_key_entity.permissions,
            "rate_limit_override": api_key_entity.rate_limit_override,
            "auth_source": source,
        }

        if not cache_hit and service is not None:
            try:
                await service.update_key_usage(api_key_entity)
            except Exception as e:
                logger.warning(f"Failed to update API key usage: {e}")

        logger.debug(
            f"Webhook API key authentication successful: key_id={api_key_entity.id}, source={source}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook API key authentication error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Authentication error")
