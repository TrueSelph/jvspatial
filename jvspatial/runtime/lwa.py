"""Best-effort AWS Lambda environment defaults for LWA and deferred-task helpers."""

from __future__ import annotations

import os
from typing import Any, Optional

from jvspatial.api.constants import deferred_invoke_http_path
from jvspatial.runtime.serverless import detect_serverless_provider, is_serverless_mode


def apply_aws_lwa_env_defaults(config: Optional[Any] = None) -> None:
    """Apply ``os.environ.setdefault`` for LWA and EventBridge when serverless on AWS.

    Also invoked from :func:`jvspatial.env.load_env` on first cache fill so
    ``AWS_LWA_PASS_THROUGH_PATH`` defaults to ``{JVSPATIAL_API_PREFIX}/_internal/deferred``
    (typically ``/api/_internal/deferred``) without IaC. The LWA **extension** may
    still read ``AWS_LWA_*`` before the Python process starts—set the same values in
    Lambda configuration when the runtime reads env before ``load_env`` runs.
    ``JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED``
    defaults to ``true`` so timed ``run_at`` work tries EventBridge first; you
    must still set ``JVSPATIAL_EVENTBRIDGE_ROLE_ARN`` (and typically
    ``AWS_ACCOUNT_ID`` if not using ``JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN``) for
    schedules to succeed—otherwise code falls back to Lambda async invoke.
    """
    if not is_serverless_mode(config):
        return
    if detect_serverless_provider() != "aws":
        return
    path = deferred_invoke_http_path()
    os.environ.setdefault("AWS_LWA_PASS_THROUGH_PATH", path)
    os.environ.setdefault("AWS_LWA_INVOKE_MODE", "RESPONSE_STREAM")
    os.environ.setdefault("JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED", "true")
