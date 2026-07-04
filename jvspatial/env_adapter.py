"""Canonical environment → :class:`~jvspatial.api.config.ServerConfig` mapping."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from jvspatial.env import parse_bool
from jvspatial.runtime.eventbridge_readiness import resolve_eventbridge_lambda_arn

logger = logging.getLogger(__name__)


def _parse_bool(val: str) -> bool:
    """Permissive boolean parser; consolidated with :func:`jvspatial.env.parse_bool`.

    Accepts ``true/false``, ``1/0``, ``yes/no``, ``on/off`` (case
    insensitive). Falls back to ``False`` for unrecognized values rather
    than raising — preserves prior behavior for misconfigured env values
    (audit §7.2-§7.3).
    """
    try:
        return parse_bool(val)
    except ValueError:
        logger.warning(
            "env_adapter: unrecognized boolean env value %r; treating as False. "
            "Use one of: true/false, 1/0, yes/no, on/off.",
            val,
        )
        return False


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

    if "JVSPATIAL_SCHEDULER_ENABLED" in os.environ:
        o["scheduler_enabled"] = _parse_bool(os.environ["JVSPATIAL_SCHEDULER_ENABLED"])
    if (n := _opt_int("JVSPATIAL_SCHEDULER_INTERVAL")) is not None:
        o["scheduler_interval"] = n

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


# Canonical allowlist of every ``JVSPATIAL_*`` environment variable the
# library reads. Anything outside this set is rejected at startup so
# typos (``JVSPATIAL_JWT_SECRET`` for ``JVSPATIAL_JWT_SECRET_KEY`` and
# similar) surface immediately rather than silently no-op'ing.
# SPEC §10.2: "Unknown JVSPATIAL_* keys are rejected at startup to catch
# typos and removed settings." Audit §7.1 closed.
ALLOWED_ENV_KEYS: frozenset[str] = frozenset(
    {
        # API metadata / server runtime
        "JVSPATIAL_TITLE",
        "JVSPATIAL_API_TITLE",
        "JVSPATIAL_DESCRIPTION",
        "JVSPATIAL_API_DESCRIPTION",
        "JVSPATIAL_VERSION",
        "JVSPATIAL_API_VERSION",
        "JVSPATIAL_API_PREFIX",
        "JVSPATIAL_API_HEALTH",
        "JVSPATIAL_API_ROOT",
        "JVSPATIAL_HOST",
        "JVSPATIAL_PORT",
        "JVSPATIAL_DEBUG",
        "JVSPATIAL_LOG_LEVEL",
        "JVSPATIAL_GRAPH_ENDPOINT_ENABLED",
        "JVSPATIAL_ENVIRONMENT",
        "JVSPATIAL_DOCS_DISABLED",
        # Database
        "JVSPATIAL_DB_TYPE",
        "JVSPATIAL_DB_PATH",
        "JVSPATIAL_MONGODB_URI",
        "JVSPATIAL_MONGODB_DB_NAME",
        "JVSPATIAL_MONGODB_MAX_POOL_SIZE",
        "JVSPATIAL_MONGODB_MIN_POOL_SIZE",
        "JVSPATIAL_POSTGRES_DSN",
        "JVSPATIAL_POSTGRES_MIN_POOL_SIZE",
        "JVSPATIAL_POSTGRES_MAX_POOL_SIZE",
        "JVSPATIAL_POSTGRES_POOLER_MODE",
        "JVSPATIAL_DYNAMODB_TABLE_NAME",
        "JVSPATIAL_DYNAMODB_REGION",
        "JVSPATIAL_DYNAMODB_ENDPOINT_URL",
        "JVSPATIAL_DYNAMODB_WAIT_FOR_INDEX",
        "JVSPATIAL_AUTO_CREATE_INDEXES",
        # Auth
        "JVSPATIAL_AUTH_ENABLED",
        "JVSPATIAL_AUTH_STRICT_HASHING",
        "JVSPATIAL_AUTH_BLACKLIST_FAIL_CLOSED",
        "JVSPATIAL_JWT_SECRET_KEY",
        "JVSPATIAL_JWT_ALGORITHM",
        "JVSPATIAL_JWT_EXPIRE_MINUTES",
        "JVSPATIAL_JWT_REFRESH_EXPIRE_DAYS",
        "JVSPATIAL_BCRYPT_ROUNDS",
        "JVSPATIAL_BCRYPT_ROUNDS_SERVERLESS",
        # CORS
        "JVSPATIAL_CORS_ENABLED",
        "JVSPATIAL_CORS_ORIGINS",
        "JVSPATIAL_CORS_METHODS",
        "JVSPATIAL_CORS_HEADERS",
        # Rate limiting
        "JVSPATIAL_RATE_LIMIT_ENABLED",
        "JVSPATIAL_RATE_LIMIT_DEFAULT_REQUESTS",
        "JVSPATIAL_RATE_LIMIT_DEFAULT_WINDOW",
        # File storage
        "JVSPATIAL_FILE_STORAGE_ENABLED",
        "JVSPATIAL_FILE_STORAGE_PROVIDER",
        "JVSPATIAL_FILE_STORAGE_BASE_URL",
        "JVSPATIAL_FILE_STORAGE_MAX_SIZE",
        "JVSPATIAL_FILE_STORAGE_SERVERLESS_SHARED",
        "JVSPATIAL_FILES_ROOT_PATH",
        "JVSPATIAL_FILES_PUBLIC_READ",
        "JVSPATIAL_FILE_INTERFACE",
        "JVSPATIAL_S3_BUCKET_NAME",
        "JVSPATIAL_S3_REGION",
        "JVSPATIAL_S3_ACCESS_KEY",
        "JVSPATIAL_S3_SECRET_KEY",
        "JVSPATIAL_S3_ENDPOINT_URL",
        "JVSPATIAL_S3_MULTIPART_THRESHOLD",
        # URL proxy
        "JVSPATIAL_PROXY_ENABLED",
        "JVSPATIAL_PROXY_DEFAULT_EXPIRATION",
        "JVSPATIAL_PROXY_MAX_EXPIRATION",
        "JVSPATIAL_PROXY_PREFIX",
        # Cache
        "JVSPATIAL_CACHE_BACKEND",
        "JVSPATIAL_CACHE_SIZE",
        "JVSPATIAL_REDIS_URL",
        "JVSPATIAL_REDIS_TTL",
        "JVSPATIAL_REDIS_SERIALIZATION",
        "JVSPATIAL_FAST_DESERIALIZE",
        # Scheduler / deferred / serverless
        "JVSPATIAL_SCHEDULER_ENABLED",
        "JVSPATIAL_SCHEDULER_INTERVAL",
        "JVSPATIAL_DEFERRED_TASK_PROVIDER",
        "JVSPATIAL_DEFERRED_INVOKE_DISABLED",
        "JVSPATIAL_DEFERRED_INVOKE_SECRET",
        "JVSPATIAL_ENABLE_DEFERRED_SAVES",
        "JVSPATIAL_AWS_DEFERRED_TRANSPORT",
        "JVSPATIAL_AWS_SQS_QUEUE_URL",
        "JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN",
        "JVSPATIAL_EVENTBRIDGE_ROLE_ARN",
        "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED",
        "JVSPATIAL_EVENTBRIDGE_SCHEDULER_GROUP",
        "JVSPATIAL_LWA_ENV_DEFAULTS",
        # Webhooks
        "JVSPATIAL_WEBHOOK_HMAC_ALGORITHM",
        "JVSPATIAL_WEBHOOK_HMAC_SECRET",
        "JVSPATIAL_WEBHOOK_HTTPS_REQUIRED",
        "JVSPATIAL_WEBHOOK_IDEMPOTENCY_TTL",
        "JVSPATIAL_WEBHOOK_MAX_PAYLOAD_SIZE",
        # Walkers
        "JVSPATIAL_WALKER_MAX_STEPS",
        "JVSPATIAL_WALKER_MAX_VISITS_PER_NODE",
        "JVSPATIAL_WALKER_MAX_EXECUTION_TIME",
        "JVSPATIAL_WALKER_MAX_QUEUE_SIZE",
        "JVSPATIAL_WALKER_MAX_TRAIL_LENGTH",
        "JVSPATIAL_WALKER_PROTECTION_ENABLED",
        # Observability (ObservableDatabase wrapper — db/_observable.py,
        # read directly via os.environ in api/components/database_configurator.py)
        "JVSPATIAL_OBSERVABILITY_ENABLED",
        "JVSPATIAL_SLOW_QUERY_MS",
        # Logging
        "JVSPATIAL_DB_LOGGING_ENABLED",
        "JVSPATIAL_DB_LOGGING_API_ENABLED",
        "JVSPATIAL_DB_LOGGING_DB_NAME",
        "JVSPATIAL_DB_LOGGING_LEVELS",
        "JVSPATIAL_DB_LOG_SERVERLESS_ASYNC",
        "JVSPATIAL_DB_LOG_SERVERLESS_JOIN_TIMEOUT",
        "JVSPATIAL_LOG_DB_TYPE",
        "JVSPATIAL_LOG_DB_NAME",
        "JVSPATIAL_LOG_DB_PATH",
        "JVSPATIAL_LOG_DB_URI",
        "JVSPATIAL_LOG_DB_REGION",
        "JVSPATIAL_LOG_DB_TABLE_NAME",
        "JVSPATIAL_LOG_DB_ENDPOINT_URL",
        # Collections
        "JVSPATIAL_COLLECTION_API_KEYS",
        "JVSPATIAL_COLLECTION_SCHEDULED_TASKS",
        "JVSPATIAL_COLLECTION_SESSIONS",
        "JVSPATIAL_COLLECTION_USERS",
        "JVSPATIAL_COLLECTION_WEBHOOKS",
        "JVSPATIAL_COLLECTION_WEBHOOK_REQUESTS",
        # Work-claim helpers
        "JVSPATIAL_WORK_CLAIM_STALE_SECONDS",
        # Misc
        "JVSPATIAL_TEXT_NORMALIZATION_ENABLED",
        "JVSPATIAL_EXPOSE_ERROR_DETAILS",
        "JVSPATIAL_STRICT_ENV_ALLOWLIST",
    }
)


def discover_unknown_jvspatial_env_keys() -> List[str]:
    """Return any ``JVSPATIAL_*`` env keys not present in :data:`ALLOWED_ENV_KEYS`.

    Pure helper — callers decide the strictness of the response.
    """
    return sorted(
        k
        for k in os.environ
        if k.startswith("JVSPATIAL_") and k not in ALLOWED_ENV_KEYS
    )


def enforce_env_allowlist() -> None:
    """Reject (strict) or warn (default) on unknown ``JVSPATIAL_*`` env keys.

    Toggled by ``JVSPATIAL_STRICT_ENV_ALLOWLIST``: when truthy, unknown
    keys raise ``ValueError`` at server startup, surfacing typos
    immediately. Default emits a single warning per unknown key per
    process so existing deployments don't break on upgrade.

    Closes audit §7.1 / SPEC §10.2.
    """
    unknown = discover_unknown_jvspatial_env_keys()
    if not unknown:
        return

    strict = False
    raw_strict = os.environ.get("JVSPATIAL_STRICT_ENV_ALLOWLIST", "").strip()
    if raw_strict:
        try:
            strict = parse_bool(raw_strict)
        except ValueError:
            strict = False

    if strict:
        raise ValueError(
            "Unknown JVSPATIAL_* environment variables detected: "
            + ", ".join(unknown)
            + ". Either remove the variable or add it to ALLOWED_ENV_KEYS in "
            "jvspatial/env_adapter.py."
        )
    for key in unknown:
        logger.warning(
            "Unknown JVSPATIAL_* env var %r ignored. Set "
            "JVSPATIAL_STRICT_ENV_ALLOWLIST=true to fail-fast on typos.",
            key,
        )


def validate_server_config_requirements(config: Any) -> None:
    """Raise ``ValueError`` when required settings for enabled features are missing."""
    enforce_env_allowlist()
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
