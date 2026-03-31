"""EventBridge Scheduler prerequisites (role + resolvable Lambda target ARN)."""

from __future__ import annotations

import os
from typing import Any


def aws_region_from_environ() -> str:
    """Region for composed Lambda ARNs; mirrors :class:`~jvspatial.env.EnvConfig` merge order."""
    return (
        os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
    ).strip() or "us-east-1"


def resolve_eventbridge_lambda_arn_from_values(
    eventbridge_lambda_arn: str,
    aws_lambda_function_name: str,
    aws_region: str,
    aws_account_id: str,
) -> str:
    """Resolve target Lambda ARN from env-style fields (explicit ARN or compose from AWS_*)."""
    arn = (eventbridge_lambda_arn or "").strip()
    if arn:
        return arn
    func_name = (aws_lambda_function_name or "").strip()
    if func_name:
        account = (aws_account_id or "").strip()
        if account:
            region = (aws_region or "").strip() or "us-east-1"
            return f"arn:aws:lambda:{region}:{account}:function:{func_name}"
    return ""


def resolve_eventbridge_lambda_arn(e: Any) -> str:
    """Resolve target Lambda ARN from a loaded :func:`~jvspatial.env.load_env` config object."""
    return resolve_eventbridge_lambda_arn_from_values(
        getattr(e, "eventbridge_lambda_arn", "") or "",
        getattr(e, "aws_lambda_function_name", "") or "",
        getattr(e, "aws_region", "") or "us-east-1",
        getattr(e, "aws_account_id", "") or "",
    )


def eventbridge_scheduler_prerequisites_met(e: Any) -> bool:
    """True when role ARN and resolvable Lambda target ARN are both non-empty."""
    role = (getattr(e, "eventbridge_role_arn", "") or "").strip()
    if not role:
        return False
    return bool(resolve_eventbridge_lambda_arn(e).strip())


def eventbridge_scheduler_prerequisites_met_from_environ() -> bool:
    """Prerequisites using ``os.environ`` only (before/without ``load_env`` cache)."""
    role = os.getenv("JVSPATIAL_EVENTBRIDGE_ROLE_ARN", "").strip()
    if not role:
        return False
    lam = resolve_eventbridge_lambda_arn_from_values(
        os.getenv("JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN", ""),
        os.getenv("AWS_LAMBDA_FUNCTION_NAME", ""),
        aws_region_from_environ(),
        os.getenv("AWS_ACCOUNT_ID", ""),
    )
    return bool(lam.strip())
