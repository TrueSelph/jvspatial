"""Canonical environment → :class:`~jvspatial.api.config.ServerConfig` mapping."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from jvspatial.runtime.eventbridge_readiness import resolve_eventbridge_lambda_arn


def _parse_bool(val: str) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes")


def _split_csv_list(raw: Optional[str]) -> Optional[List[str]]:
    if not raw or not str(raw).strip():
        return None
    return [p.strip() for p in str(raw).split(",") if p.strip()]


def _opt_str(name: str) -> Optional[str]:
    v = os.environ.get(name)
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _opt_int(name: str) -> Optional[int]:
    raw = _opt_str(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge dicts; *override* wins. None values in *override* are skipped."""
    out: Dict[str, Any] = dict(base)
    for k, v in override.items():
        if v is None:
            continue
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def server_config_overrides_from_env() -> Dict[str, Any]:
    """Build a nested dict suitable for merging into :class:`~jvspatial.api.config.ServerConfig`.

    Only includes keys that are explicitly set in the environment.
    """
    o: Dict[str, Any] = {}

    if (t := _opt_str("JVSPATIAL_TITLE")) is not None:
        o["title"] = t
    if (t := _opt_str("JVSPATIAL_API_TITLE")) is not None:
        o["title"] = t
    if (t := _opt_str("JVSPATIAL_DESCRIPTION")) is not None:
        o["description"] = t
    if (t := _opt_str("JVSPATIAL_API_DESCRIPTION")) is not None:
        o["description"] = t
    if (t := _opt_str("JVSPATIAL_VERSION")) is not None:
        o["version"] = t
    if (t := _opt_str("JVSPATIAL_API_VERSION")) is not None:
        o["version"] = t

    if (t := _opt_str("JVSPATIAL_HOST")) is not None:
        o["host"] = t
    if (p := _opt_int("JVSPATIAL_PORT")) is not None:
        o["port"] = p
    if "JVSPATIAL_DEBUG" in os.environ:
        o["debug"] = _parse_bool(os.environ["JVSPATIAL_DEBUG"])
    if (raw_graph := os.environ.get("JVSPATIAL_GRAPH_ENDPOINT_ENABLED")) is not None:
        s = str(raw_graph).strip()
        if s:
            o["graph_endpoint_enabled"] = _parse_bool(s)
    if (t := _opt_str("JVSPATIAL_LOG_LEVEL")) is not None:
        o["log_level"] = t

    if "JVSPATIAL_DEFERRED_TASK_PROVIDER" in os.environ:
        raw = os.environ.get("JVSPATIAL_DEFERRED_TASK_PROVIDER", "").strip()
        if raw:
            o["deferred_task_provider"] = raw

    db: Dict[str, Any] = {}
    if (t := _opt_str("JVSPATIAL_DB_TYPE")) is not None:
        db["db_type"] = t
    if (t := _opt_str("JVSPATIAL_DB_PATH")) is not None:
        db["db_path"] = t
    if (t := _opt_str("JVSPATIAL_MONGODB_URI")) is not None:
        db["db_connection_string"] = t
    if (t := _opt_str("JVSPATIAL_MONGODB_DB_NAME")) is not None:
        db["db_database_name"] = t
    for ek, dk in (
        ("JVSPATIAL_DYNAMODB_TABLE_NAME", "dynamodb_table_name"),
        ("JVSPATIAL_DYNAMODB_REGION", "dynamodb_region"),
        ("JVSPATIAL_DYNAMODB_ENDPOINT_URL", "dynamodb_endpoint_url"),
    ):
        if (t := _opt_str(ek)) is not None:
            db[dk] = t
    if db:
        o["database"] = db

    cors: Dict[str, Any] = {}
    if "JVSPATIAL_CORS_ENABLED" in os.environ:
        cors["cors_enabled"] = _parse_bool(os.environ["JVSPATIAL_CORS_ENABLED"])
    if (
        origins := _split_csv_list(os.environ.get("JVSPATIAL_CORS_ORIGINS"))
    ) is not None:
        cors["cors_origins"] = origins
    if (
        methods := _split_csv_list(os.environ.get("JVSPATIAL_CORS_METHODS"))
    ) is not None:
        cors["cors_methods"] = methods
    if (
        headers := _split_csv_list(os.environ.get("JVSPATIAL_CORS_HEADERS"))
    ) is not None:
        cors["cors_headers"] = headers
    if cors:
        o["cors"] = cors

    auth: Dict[str, Any] = {}
    if "JVSPATIAL_AUTH_ENABLED" in os.environ:
        auth["auth_enabled"] = _parse_bool(os.environ["JVSPATIAL_AUTH_ENABLED"])
    if (t := _opt_str("JVSPATIAL_JWT_SECRET_KEY")) is not None:
        auth["jwt_secret"] = t
    if (t := _opt_str("JVSPATIAL_JWT_ALGORITHM")) is not None:
        auth["jwt_algorithm"] = t
    if (m := _opt_int("JVSPATIAL_JWT_EXPIRE_MINUTES")) is not None:
        auth["jwt_expire_minutes"] = m
    if (d := _opt_int("JVSPATIAL_JWT_REFRESH_EXPIRE_DAYS")) is not None:
        auth["refresh_expire_days"] = d
    if auth:
        o["auth"] = auth

    rl: Dict[str, Any] = {}
    if "JVSPATIAL_RATE_LIMIT_ENABLED" in os.environ:
        rl["rate_limit_enabled"] = _parse_bool(
            os.environ["JVSPATIAL_RATE_LIMIT_ENABLED"]
        )
    if (n := _opt_int("JVSPATIAL_RATE_LIMIT_DEFAULT_REQUESTS")) is not None:
        rl["rate_limit_default_requests"] = n
    if (w := _opt_int("JVSPATIAL_RATE_LIMIT_DEFAULT_WINDOW")) is not None:
        rl["rate_limit_default_window"] = w
    if rl:
        o["rate_limit"] = rl

    fs: Dict[str, Any] = {}
    if "JVSPATIAL_FILE_STORAGE_ENABLED" in os.environ:
        fs["file_storage_enabled"] = _parse_bool(
            os.environ["JVSPATIAL_FILE_STORAGE_ENABLED"]
        )
    if (t := _opt_str("JVSPATIAL_FILE_STORAGE_PROVIDER")) is not None:
        fs["file_storage_provider"] = t
    if (t := _opt_str("JVSPATIAL_FILES_ROOT_PATH")) is not None:
        fs["file_storage_root"] = t
    if (t := _opt_str("JVSPATIAL_FILE_STORAGE_BASE_URL")) is not None:
        fs["file_storage_base_url"] = t
    if (n := _opt_int("JVSPATIAL_FILE_STORAGE_MAX_SIZE")) is not None:
        fs["file_storage_max_size"] = n
    for ek, fk in (
        ("JVSPATIAL_S3_BUCKET_NAME", "s3_bucket_name"),
        ("JVSPATIAL_S3_REGION", "s3_region"),
        ("JVSPATIAL_S3_ACCESS_KEY", "s3_access_key"),
        ("JVSPATIAL_S3_SECRET_KEY", "s3_secret_key"),
        ("JVSPATIAL_S3_ENDPOINT_URL", "s3_endpoint_url"),
    ):
        if (t := _opt_str(ek)) is not None:
            fs[fk] = t
    if fs:
        o["file_storage"] = fs

    proxy: Dict[str, Any] = {}
    if "JVSPATIAL_PROXY_ENABLED" in os.environ:
        proxy["proxy_enabled"] = _parse_bool(os.environ["JVSPATIAL_PROXY_ENABLED"])
    if (n := _opt_int("JVSPATIAL_PROXY_DEFAULT_EXPIRATION")) is not None:
        proxy["proxy_default_expiration"] = n
    if (n := _opt_int("JVSPATIAL_PROXY_MAX_EXPIRATION")) is not None:
        proxy["proxy_max_expiration"] = n
    if proxy:
        o["proxy"] = proxy

    return o


def validate_server_config_requirements(config: Any) -> None:
    """Raise ``ValueError`` when required settings for enabled features are missing."""
    auth = config.auth
    if auth.auth_enabled:
        secret = (auth.jwt_secret or "").strip()
        if not secret:
            raise ValueError(
                "Authentication is enabled but jwt_secret is empty. "
                "Set JVSPATIAL_JWT_SECRET_KEY or pass auth.jwt_secret in Server config."
            )

    fs = config.file_storage
    if (
        fs.file_storage_enabled
        and (fs.file_storage_provider or "").strip().lower() == "s3"
    ):
        if not (fs.s3_bucket_name or "").strip():
            raise ValueError(
                "S3 file storage requires JVSPATIAL_S3_BUCKET_NAME / s3_bucket_name."
            )
        if not (fs.s3_region or "").strip():
            raise ValueError(
                "S3 file storage requires JVSPATIAL_S3_REGION / s3_region."
            )
        if not (fs.s3_access_key or "").strip():
            raise ValueError(
                "S3 file storage requires JVSPATIAL_S3_ACCESS_KEY / s3_access_key."
            )
        if not (fs.s3_secret_key or "").strip():
            raise ValueError(
                "S3 file storage requires JVSPATIAL_S3_SECRET_KEY / s3_secret_key."
            )

    from jvspatial.env import env

    backend = env("JVSPATIAL_CACHE_BACKEND", default="memory").lower()
    redis_url_set = bool(env("JVSPATIAL_REDIS_URL", default=""))
    needs_redis = backend in ("redis", "layered") or (
        backend == "memory" and redis_url_set
    )
    if needs_redis and not redis_url_set:
        raise ValueError(
            "Redis-backed cache requires JVSPATIAL_REDIS_URL "
            f"(cache backend resolves to redis/layered; JVSPATIAL_CACHE_BACKEND={backend!r})."
        )

    if env("JVSPATIAL_AWS_DEFERRED_TRANSPORT", default="").lower() == "sqs" and not env(
        "JVSPATIAL_AWS_SQS_QUEUE_URL", default=""
    ):
        raise ValueError(
            "JVSPATIAL_AWS_DEFERRED_TRANSPORT=sqs requires JVSPATIAL_AWS_SQS_QUEUE_URL."
        )

    eb_raw = env("JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED", default="").lower()
    if eb_raw in ("true", "1", "yes"):
        role = env("JVSPATIAL_EVENTBRIDGE_ROLE_ARN", default="")
        if not role:
            raise ValueError(
                "EventBridge scheduler enabled requires JVSPATIAL_EVENTBRIDGE_ROLE_ARN."
            )

        class _EnvView:
            eventbridge_lambda_arn = env("JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN", default="")
            aws_lambda_function_name = env("AWS_LAMBDA_FUNCTION_NAME", default="")
            aws_region = (
                env(
                    "AWS_REGION", default=env("AWS_DEFAULT_REGION", default="us-east-1")
                )
                or "us-east-1"
            )
            aws_account_id = env("AWS_ACCOUNT_ID", default="")

        lambda_arn = resolve_eventbridge_lambda_arn(_EnvView()).strip()
        if not lambda_arn:
            raise ValueError(
                "EventBridge scheduler enabled requires JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN "
                "or AWS_LAMBDA_FUNCTION_NAME with AWS_ACCOUNT_ID (and AWS_REGION)."
            )
        if not role.startswith("arn:") or ":iam::" not in role:
            raise ValueError(
                "JVSPATIAL_EVENTBRIDGE_ROLE_ARN must be a valid IAM role ARN "
                "(expected arn:*:iam::…)."
            )
        if not lambda_arn.startswith("arn:") or ":lambda:" not in lambda_arn:
            raise ValueError(
                "Resolved EventBridge Lambda target must be a valid Lambda function ARN "
                "(expected arn:*:lambda:…)."
            )


def warn_production_config_gaps(config: Any, logger: Any) -> None:
    """Log warnings in production when recommended settings are implicit."""
    from jvspatial.env import get_environment_mode

    if get_environment_mode() != "production":
        return
    if not (config.database.db_type or "").strip():
        logger.warning(
            "JVSPATIAL_DB_TYPE is unset in production; prime database may not initialize."
        )
    if (
        config.file_storage.file_storage_enabled
        and not (os.environ.get("JVSPATIAL_FILES_ROOT_PATH") or "").strip()
        and (config.file_storage.file_storage_provider or "local").lower() == "local"
    ):
        logger.warning(
            "JVSPATIAL_FILES_ROOT_PATH is unset in production with local file storage."
        )
    if config.auth.auth_enabled:
        secret = (config.auth.jwt_secret or "").strip()
        algo = (config.auth.jwt_algorithm or "HS256").strip().upper()
        if secret and algo.startswith("HS"):
            key_len = len(secret.encode("utf-8"))
            min_len = 32
            if algo == "HS384":
                min_len = 48
            elif algo == "HS512":
                min_len = 64
            if key_len < min_len:
                logger.warning(
                    "JWT signing secret for %s is %s bytes; PyJWT recommends at least "
                    "%s bytes for this HMAC algorithm (RFC 7518). "
                    "Use a longer JVSPATIAL_JWT_SECRET_KEY to avoid InsecureKeyLengthWarning.",
                    algo,
                    key_len,
                    min_len,
                )
