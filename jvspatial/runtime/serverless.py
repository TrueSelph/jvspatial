"""Serverless runtime detection helpers."""

import os
from functools import lru_cache
from typing import Any, Literal, Optional, cast

ServerlessProvider = Literal["aws", "azure", "gcp", "vercel", "unknown"]


def _parse_bool(val: str) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes", "enabled")


@lru_cache(maxsize=1)
def _detect_serverless_mode() -> bool:
    """Auto-detect serverless runtime based on platform environment."""

    # AWS Lambda
    if os.getenv("AWS_LAMBDA_RUNTIME_API") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return True

    # Future-ready checks
    if os.getenv("FUNCTIONS_WORKER_RUNTIME"):  # Azure Functions
        return True
    if os.getenv("K_SERVICE"):  # Google Cloud Run/Functions Gen2
        return True
    if os.getenv("VERCEL"):  # Vercel Functions
        return True

    return False


@lru_cache(maxsize=1)
def _detect_serverless_provider() -> str:
    """Infer serverless cloud provider from environment (best-effort)."""

    if os.getenv("AWS_LAMBDA_RUNTIME_API") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return "aws"
    if os.getenv("FUNCTIONS_WORKER_RUNTIME"):  # Azure Functions
        return "azure"
    if os.getenv("K_SERVICE"):  # Google Cloud Run / Functions Gen2
        return "gcp"
    if os.getenv("VERCEL"):
        return "vercel"
    return "unknown"


def detect_serverless_provider() -> ServerlessProvider:
    """Return detected provider string; use for default deferred-task backend selection."""
    return cast(ServerlessProvider, _detect_serverless_provider())


def _config_from_current_server() -> Optional[Any]:
    """Best-effort `Server.config` when `set_current_server` is in use (request scope)."""
    try:
        from jvspatial.api.context import get_current_server

        srv = get_current_server()
        if srv is not None:
            return getattr(srv, "config", None)
    except ImportError:
        pass
    return None


def is_serverless_mode(config: Optional[Any] = None) -> bool:
    """Return effective serverless mode.

    Precedence:
    1. explicit ``config.serverless_mode`` when *config* is provided and the
       attribute is set (not None)
    2. same as (1) using :func:`get_current_server` when *config* is omitted
    3. ``SERVERLESS_MODE`` env var override
    4. runtime auto-detection
    """
    effective = config
    if effective is None:
        effective = _config_from_current_server()
    if (
        effective is not None
        and getattr(effective, "serverless_mode", None) is not None
    ):
        return bool(effective.serverless_mode)
    override = os.getenv("SERVERLESS_MODE", "").strip()
    if override:
        return _parse_bool(override)
    return _detect_serverless_mode()


def reset_serverless_mode_cache() -> None:
    """Reset memoized detection results (primarily for tests)."""
    _detect_serverless_mode.cache_clear()
    _detect_serverless_provider.cache_clear()
