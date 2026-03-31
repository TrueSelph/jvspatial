"""Canonical environment → :class:`~jvspatial.api.config.ServerConfig` mapping.

Strict JVSPATIAL_* validation (forbidden and unknown keys) runs when constructing
:class:`~jvspatial.api.server.Server`. :func:`assert_no_forbidden_jvspatial_env`
runs from :func:`~jvspatial.env.load_env` so removed keys fail even without Server.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# Keys that must not appear (clean break — no aliases).
FORBIDDEN_JVSPATIAL_KEYS: frozenset[str] = frozenset(
    {
        "JVSPATIAL_DB_URI",
        "JVSPATIAL_DB_NAME",
        "JVSPATIAL_JSONDB_PATH",
        "JVSPATIAL_SQLITE_PATH",
        "JVSPATIAL_STORAGE_ENABLED",
        "JVSPATIAL_STORAGE_PROVIDER",
        "JVSPATIAL_STORAGE_ROOT",
        "JVSPATIAL_S3_REGION_NAME",
        "JVSPATIAL_S3_ACCESS_KEY_ID",
        "JVSPATIAL_S3_SECRET_ACCESS_KEY",
        "JVSPATIAL_JWT_EXPIRATION_HOURS",
        "JVSPATIAL_JWT_REFRESH_EXPIRATION_DAYS",
        "JVSPATIAL_L1_SIZE",
        "JVSPATIAL_PROXY_EXPIRATION",
    }
)

# Every JVSPATIAL_* key understood by jvspatial (library + server). Server startup
# rejects any JVSPATIAL_* not in this set.
ALLOWED_JVSPATIAL_KEYS: frozenset[str] = frozenset(
    {
        "JVSPATIAL_DB_TYPE",
        "JVSPATIAL_DB_PATH",
        "JVSPATIAL_MONGODB_URI",
        "JVSPATIAL_MONGODB_DB_NAME",
        "JVSPATIAL_MONGODB_MAX_POOL_SIZE",
        "JVSPATIAL_MONGODB_MIN_POOL_SIZE",
        "JVSPATIAL_DYNAMODB_TABLE_NAME",
        "JVSPATIAL_DYNAMODB_REGION",
        "JVSPATIAL_DYNAMODB_ENDPOINT_URL",
        "JVSPATIAL_DYNAMODB_WAIT_FOR_INDEX",
        "JVSPATIAL_WEBHOOK_HMAC_SECRET",
        "JVSPATIAL_WEBHOOK_HMAC_ALGORITHM",
        "JVSPATIAL_WEBHOOK_MAX_PAYLOAD_SIZE",
        "JVSPATIAL_WEBHOOK_IDEMPOTENCY_TTL",
        "JVSPATIAL_WEBHOOK_HTTPS_REQUIRED",
        "JVSPATIAL_WALKER_MAX_STEPS",
        "JVSPATIAL_WALKER_MAX_VISITS_PER_NODE",
        "JVSPATIAL_WALKER_MAX_EXECUTION_TIME",
        "JVSPATIAL_WALKER_MAX_QUEUE_SIZE",
        "JVSPATIAL_WALKER_PROTECTION_ENABLED",
        "JVSPATIAL_AUTO_CREATE_INDEXES",
        "JVSPATIAL_TEXT_NORMALIZATION_ENABLED",
        "JVSPATIAL_S3_BUCKET_NAME",
        "JVSPATIAL_S3_REGION",
        "JVSPATIAL_S3_ACCESS_KEY",
        "JVSPATIAL_S3_SECRET_KEY",
        "JVSPATIAL_S3_ENDPOINT_URL",
        "JVSPATIAL_WORK_CLAIM_STALE_SECONDS",
        "JVSPATIAL_DEFERRED_INVOKE_DISABLED",
        "JVSPATIAL_DEFERRED_INVOKE_SECRET",
        "JVSPATIAL_API_PREFIX",
        "JVSPATIAL_API_HEALTH",
        "JVSPATIAL_API_ROOT",
        "JVSPATIAL_FILES_PUBLIC_READ",
        "JVSPATIAL_PROXY_PREFIX",
        "JVSPATIAL_COLLECTION_USERS",
        "JVSPATIAL_COLLECTION_API_KEYS",
        "JVSPATIAL_COLLECTION_SESSIONS",
        "JVSPATIAL_COLLECTION_WEBHOOKS",
        "JVSPATIAL_COLLECTION_WEBHOOK_REQUESTS",
        "JVSPATIAL_COLLECTION_SCHEDULED_TASKS",
        "JVSPATIAL_API_TITLE",
        "JVSPATIAL_API_VERSION",
        "JVSPATIAL_API_DESCRIPTION",
        "JVSPATIAL_HOST",
        "JVSPATIAL_PORT",
        "JVSPATIAL_LOG_LEVEL",
        "JVSPATIAL_DEBUG",
        "JVSPATIAL_CORS_ENABLED",
        "JVSPATIAL_CORS_ORIGINS",
        "JVSPATIAL_CORS_METHODS",
        "JVSPATIAL_CORS_HEADERS",
        "JVSPATIAL_FILE_STORAGE_ENABLED",
        "JVSPATIAL_FILE_STORAGE_PROVIDER",
        "JVSPATIAL_FILES_ROOT_PATH",
        "JVSPATIAL_FILE_STORAGE_BASE_URL",
        "JVSPATIAL_FILE_STORAGE_MAX_SIZE",
        "JVSPATIAL_FILE_STORAGE_SERVERLESS_SHARED",
        "JVSPATIAL_PROXY_ENABLED",
        "JVSPATIAL_PROXY_DEFAULT_EXPIRATION",
        "JVSPATIAL_PROXY_MAX_EXPIRATION",
        "JVSPATIAL_DB_LOGGING_ENABLED",
        "JVSPATIAL_DB_LOGGING_LEVELS",
        "JVSPATIAL_DB_LOGGING_DB_NAME",
        "JVSPATIAL_DB_LOGGING_API_ENABLED",
        "JVSPATIAL_LOG_DB_TYPE",
        "JVSPATIAL_LOG_DB_PATH",
        "JVSPATIAL_LOG_DB_URI",
        "JVSPATIAL_LOG_DB_NAME",
        "JVSPATIAL_LOG_DB_TABLE_NAME",
        "JVSPATIAL_LOG_DB_REGION",
        "JVSPATIAL_LOG_DB_ENDPOINT_URL",
        "JVSPATIAL_LOG_RETENTION_DEFAULT_DAYS",
        "JVSPATIAL_CACHE_BACKEND",
        "JVSPATIAL_CACHE_SIZE",
        "JVSPATIAL_REDIS_URL",
        "JVSPATIAL_REDIS_TTL",
        "JVSPATIAL_L1_CACHE_SIZE",
        "JVSPATIAL_AUTH_STRICT_HASHING",
        "JVSPATIAL_BCRYPT_ROUNDS",
        "JVSPATIAL_BCRYPT_ROUNDS_SERVERLESS",
        "JVSPATIAL_ARGON2_TIME_COST",
        "JVSPATIAL_ARGON2_MEMORY_COST",
        "JVSPATIAL_ARGON2_PARALLELISM",
        "JVSPATIAL_ENABLE_DEFERRED_SAVES",
        "JVSPATIAL_DEFERRED_TASK_PROVIDER",
        "JVSPATIAL_AWS_DEFERRED_TRANSPORT",
        "JVSPATIAL_AWS_SQS_QUEUE_URL",
        "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED",
        "JVSPATIAL_EVENTBRIDGE_ROLE_ARN",
        "JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN",
        "JVSPATIAL_EVENTBRIDGE_SCHEDULER_GROUP",
        "JVSPATIAL_FILE_INTERFACE",
        "JVSPATIAL_LWA_ENV_DEFAULTS",
        "JVSPATIAL_DB_LOG_SERVERLESS_ASYNC",
        "JVSPATIAL_DB_LOG_SERVERLESS_JOIN_TIMEOUT",
        "JVSPATIAL_AUTH_ENABLED",
        "JVSPATIAL_JWT_SECRET_KEY",
        "JVSPATIAL_JWT_ALGORITHM",
        "JVSPATIAL_JWT_EXPIRE_MINUTES",
        "JVSPATIAL_JWT_REFRESH_EXPIRE_DAYS",
        "JVSPATIAL_RATE_LIMIT_ENABLED",
        "JVSPATIAL_RATE_LIMIT_DEFAULT_REQUESTS",
        "JVSPATIAL_RATE_LIMIT_DEFAULT_WINDOW",
        "JVSPATIAL_TITLE",
        "JVSPATIAL_DESCRIPTION",
        "JVSPATIAL_VERSION",
        "JVSPATIAL_GRAPH_ENDPOINT_ENABLED",
    }
)


class JvspatialConfigEnvError(ValueError):
    """Invalid or unsupported JVSPATIAL_* environment configuration."""


def assert_no_forbidden_jvspatial_env() -> None:
    """Raise if any forbidden ``JVSPATIAL_*`` key is set."""
    for key in FORBIDDEN_JVSPATIAL_KEYS:
        if key in os.environ:
            raise JvspatialConfigEnvError(
                f"Unsupported environment variable {key!r} was removed in this "
                f"release; see jvspatial docs for canonical replacement keys."
            )


def validate_known_jvspatial_env_keys() -> None:
    """Raise if any set ``JVSPATIAL_*`` key is not in the allowlist (Server startup)."""
    for key in os.environ:
        if not key.startswith("JVSPATIAL_"):
            continue
        if key not in ALLOWED_JVSPATIAL_KEYS:
            raise JvspatialConfigEnvError(
                f"Unknown environment variable {key!r}. "
                f"See docs/md/environment-configuration.md for supported JVSPATIAL_* keys."
            )


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

    # Cache: redis / layered needs Redis URL in environment (create_default_cache uses load_env).
    from jvspatial.env import load_env

    e = load_env()
    backend = (e.cache_backend or "memory").strip().lower()
    redis_url_set = bool((e.redis_url or "").strip())
    needs_redis = backend in ("redis", "layered") or (
        backend == "memory" and redis_url_set
    )
    if needs_redis and not redis_url_set:
        raise ValueError(
            "Redis-backed cache requires JVSPATIAL_REDIS_URL "
            f"(cache backend resolves to redis/layered; JVSPATIAL_CACHE_BACKEND={backend!r})."
        )

    if (e.aws_deferred_transport or "").strip().lower() == "sqs" and not (
        e.aws_sqs_queue_url or ""
    ).strip():
        raise ValueError(
            "JVSPATIAL_AWS_DEFERRED_TRANSPORT=sqs requires JVSPATIAL_AWS_SQS_QUEUE_URL."
        )

    eb_raw = (e.eventbridge_scheduler_enabled_raw or "").strip().lower()
    if eb_raw in ("true", "1", "yes"):
        if not (e.eventbridge_role_arn or "").strip():
            raise ValueError(
                "EventBridge scheduler enabled requires JVSPATIAL_EVENTBRIDGE_ROLE_ARN."
            )
        if not (e.eventbridge_lambda_arn or "").strip():
            raise ValueError(
                "EventBridge scheduler enabled requires JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN."
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
