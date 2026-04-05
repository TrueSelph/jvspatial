"""AWS serverless runtime helpers (EventBridge scheduler, LWA env defaults)."""

from __future__ import annotations

import os
from typing import Any, Optional

from jvspatial.runtime.eventbridge_readiness import (
    eventbridge_scheduler_prerequisites_met_from_environ,
)
from jvspatial.runtime.serverless import detect_serverless_provider, is_serverless_mode

_DEFERRED_INVOKE_SUFFIX = "/_internal/deferred"
_EB_SCHEDULER_KEY = "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED"
_LWA_ENV_DEFAULTS_KEY = "JVSPATIAL_LWA_ENV_DEFAULTS"


def _deferred_invoke_pass_through_path() -> str:
    """Match :meth:`jvspatial.api.constants.APIRoutes.deferred_invoke_full_path`."""
    raw = os.environ.get("JVSPATIAL_API_PREFIX", "/api")
    prefix = str(raw).strip().rstrip("/")
    suffix = _DEFERRED_INVOKE_SUFFIX
    return f"{prefix}{suffix}" if prefix else suffix


def _lambda_web_adapter_env_toggle() -> Optional[bool]:
    """Parse ``JVSPATIAL_LWA_ENV_DEFAULTS``: True=force on, False=opt out, None=auto."""
    raw = os.environ.get(_LWA_ENV_DEFAULTS_KEY, "").strip()
    if not raw:
        return None
    low = raw.lower()
    if low in ("0", "false", "no", "off"):
        return False
    if low in ("1", "true", "yes", "on"):
        return True
    return None


def is_lambda_web_adapter_runtime() -> bool:
    """Best-effort detection of Lambda Web Adapter (zip layer or container)."""
    exec_wrapper = (os.environ.get("AWS_LAMBDA_EXEC_WRAPPER") or "").lower()
    if exec_wrapper and (
        "bootstrap" in exec_wrapper
        or "adapter" in exec_wrapper
        or "lambda-web-adapter" in exec_wrapper
    ):
        return True
    if (os.environ.get("AWS_LWA_PORT") or "").strip():
        return True
    return False


def apply_aws_eventbridge_env_default(config: Optional[Any] = None) -> None:
    """Set ``JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED`` on AWS serverless when unset.

    If the variable is **already** in the environment, it is left unchanged.

    If **absent**, sets ``true`` only when EventBridge prerequisites are met (non-empty
    ``JVSPATIAL_EVENTBRIDGE_ROLE_ARN`` and a resolvable Lambda target: either
    ``JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN`` or ``AWS_LAMBDA_FUNCTION_NAME`` +
    ``AWS_ACCOUNT_ID`` + region from ``AWS_REGION`` / ``AWS_DEFAULT_REGION``). Otherwise
    sets ``false`` so startup validation does not fail; timed ``run_at`` work falls back
    to Lambda async invoke.

    To force scheduler off, set ``JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED=false`` in env.
    """
    if not is_serverless_mode(config):
        return
    if detect_serverless_provider() != "aws":
        return
    if _EB_SCHEDULER_KEY in os.environ:
        return
    os.environ[_EB_SCHEDULER_KEY] = (
        "true" if eventbridge_scheduler_prerequisites_met_from_environ() else "false"
    )


def apply_aws_lwa_env_defaults(config: Optional[Any] = None) -> None:
    """Best-effort LWA env for deferred HTTP pass-through on AWS serverless.

    Sets (via :func:`os.environ.setdefault` only):

    - ``AWS_LWA_INVOKE_MODE=RESPONSE_STREAM``
    - ``AWS_LWA_PASS_THROUGH_PATH`` to ``{JVSPATIAL_API_PREFIX}/_internal/deferred``
      (same rule as :meth:`jvspatial.api.constants.APIRoutes.deferred_invoke_full_path`).

    Runs only when ``is_serverless_mode`` and provider is AWS, and either
    :func:`is_lambda_web_adapter_runtime` is true or ``JVSPATIAL_LWA_ENV_DEFAULTS`` is
    truthy (``1``, ``true``, ``yes``, ``on``) to force application when detection
    misses. Set ``JVSPATIAL_LWA_ENV_DEFAULTS`` to ``0``, ``false``, ``no``, or ``off``
    to skip entirely.

    The LWA extension may read these before Python starts; IaC is still recommended
    for guarantees. Runtime defaults help emulation, subprocesses, and re-read paths.
    """
    if not is_serverless_mode(config):
        return
    if detect_serverless_provider() != "aws":
        return

    toggle = _lambda_web_adapter_env_toggle()
    if toggle is False:
        return
    if toggle is not True and not is_lambda_web_adapter_runtime():
        return

    os.environ.setdefault("AWS_LWA_INVOKE_MODE", "RESPONSE_STREAM")
    os.environ.setdefault(
        "AWS_LWA_PASS_THROUGH_PATH", _deferred_invoke_pass_through_path()
    )
