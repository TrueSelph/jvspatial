"""Centralized environment variable loading for jvspatial.

Application code should read configuration via :func:`load_env` (cached) instead of
``os.getenv`` directly.

**Loaded here:** All ``JVSPATIAL_*`` settings used by the library, plus shared AWS
credential keys where applicable. Local file storage root uses
:func:`resolve_file_storage_root` from ``JVSPATIAL_FILES_ROOT_PATH`` (and config
fallback) for both :func:`load_env` and Server ``FileStorageConfig``.

**Not loaded here (avoid import cycles with :func:`load_env`):**

- ``SERVERLESS_MODE`` and cloud runtime detection — see
  :mod:`jvspatial.runtime.serverless` (``AWS_LAMBDA_RUNTIME_API``, ``AWS_LAMBDA_FUNCTION_NAME``,
  ``FUNCTIONS_WORKER_RUNTIME``, ``K_SERVICE``, ``VERCEL``, etc.).
- ``AWS_LWA_PASS_THROUGH_PATH``, ``AWS_LWA_INVOKE_MODE`` — defaulted via
  :func:`jvspatial.runtime.lwa.apply_aws_lwa_env_defaults` on first
  :func:`load_env` (AWS serverless) and again when :class:`~jvspatial.api.server.Server`
  starts. Default path is ``/api/_internal/deferred`` when ``JVSPATIAL_API_PREFIX`` is
  unset (see :func:`jvspatial.api.constants.deferred_invoke_http_path`).
- ``JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED`` — may default to ``"true"`` via
  ``os.environ.setdefault`` in :mod:`jvspatial.runtime.lwa` on AWS serverless; application
  code still reads the effective value through :func:`load_env` (cached together with other
  EventBridge fields).
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from typing import Callable, List, Literal, Optional

from jvspatial.runtime.serverless import is_serverless_mode


def _parse_bool(val: str) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes")


def _parse_bool_on(val: str) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes", "on")


def _split_csv_list(raw: Optional[str]) -> Optional[List[str]]:
    if not raw or not raw.strip():
        return None
    return [p.strip() for p in raw.split(",") if p.strip()]


def _normalize_env_str(val: Optional[str]) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def resolve_file_storage_root(
    merged_root: Optional[str] = None,
    *,
    serverless: Optional[bool] = None,
) -> str:
    """Resolve local filesystem root for stored files (jvagent + /api/storage).

    Precedence (matches jvagent ``get_file_storage_config``):

    #. ``JVSPATIAL_FILES_ROOT_PATH`` (non-empty)
    #. ``merged_root`` (e.g. YAML / pydantic-parsed value after defaults)
    #. ``/tmp/.files`` when serverless else ``./.files``

    Args:
        merged_root: Config-derived value when env is unset (may be None).
        serverless: If None, uses :func:`jvspatial.runtime.serverless.is_serverless_mode`.
    """
    if serverless is None:
        serverless = is_serverless_mode()

    files = _normalize_env_str(os.environ.get("JVSPATIAL_FILES_ROOT_PATH"))
    merged = _normalize_env_str(merged_root)

    default = "/tmp/.files" if serverless else "./.files"

    if files:
        return files
    if merged:
        return merged
    return default


_DEFAULT_DEV_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]


@dataclass
class EnvConfig:
    """Unified environment configuration for jvspatial."""

    # Database
    db_type: str
    jsondb_path: str
    db_path: str
    mongodb_uri: str
    mongodb_db_name: str
    mongodb_max_pool: Optional[int]
    mongodb_min_pool: Optional[int]
    dynamodb_table_name: str
    dynamodb_region: str
    dynamodb_endpoint_url: Optional[str]
    dynamodb_access_key_id: Optional[str]
    dynamodb_secret_access_key: Optional[str]
    dynamodb_wait_for_index: bool

    # Webhook
    webhook_hmac_secret: Optional[str]
    webhook_hmac_algorithm: str
    webhook_max_payload_size: int
    webhook_idempotency_ttl: int
    webhook_https_required: bool

    # Walker
    walker_max_steps: int
    walker_max_visits_per_node: int
    walker_max_execution_time: float
    walker_max_queue_size: int
    walker_protection_enabled: bool

    # Core
    auto_create_indexes: bool
    text_normalization_enabled: bool

    # Storage (S3)
    s3_bucket_name: Optional[str]
    s3_region_name: str
    s3_access_key_id: Optional[str]
    s3_secret_access_key: Optional[str]
    s3_endpoint_url: Optional[str]

    # Environment mode (JVAGENT_ENVIRONMENT or JVSPATIAL_ENVIRONMENT)
    environment: Optional[str]
    serverless_mode: bool

    # Work-claim leases (jvspatial.db.work_claim)
    work_claim_stale_seconds: float

    # Deferred invoke HTTP route (internal LWA pass-through)
    deferred_invoke_disabled: bool
    deferred_invoke_secret: Optional[str]

    # API routes (jvspatial.api.constants.APIRoutes)
    api_prefix: str
    api_health: str
    api_root: str
    storage_prefix: str
    proxy_prefix: str

    # Collections
    collection_users: str
    collection_api_keys: str
    collection_sessions: str
    collection_webhooks: str
    collection_webhook_requests: str
    collection_scheduled_tasks: str

    # Defaults (server / OpenAPI / CORS / file storage / URL proxy)
    api_title: str
    api_version: str
    api_description: str
    host: str
    port: int
    log_level: str
    debug: bool
    cors_enabled: bool
    cors_origins: List[str]
    cors_methods: List[str]
    cors_headers: List[str]
    file_storage_enabled: bool
    file_storage_provider: str
    file_storage_root: str
    file_storage_max_size: int
    file_storage_base_url: str
    proxy_enabled: bool
    proxy_expiration: int
    proxy_max_expiration: int

    # DB logging (jvspatial.logging.config)
    db_logging_enabled: bool
    db_logging_levels: str
    db_logging_db_name: str
    db_logging_api_enabled: bool
    log_db_type: Optional[str]
    log_db_path_json: str
    log_db_path_sqlite: str
    log_db_uri: Optional[str]
    log_db_name: str
    log_db_table_name: str
    log_db_region: Optional[str]
    log_db_endpoint_url: Optional[str]

    # Cache
    cache_backend: str
    cache_size: int
    redis_url: Optional[str]
    redis_ttl: int
    l1_cache_size: int

    # Auth hashing
    auth_strict_hashing: bool
    bcrypt_rounds: int
    bcrypt_rounds_serverless: int
    argon2_time_cost: int
    argon2_memory_cost: int
    argon2_parallelism: int

    # Deferred entity saves
    enable_deferred_saves: bool

    # Serverless deferred tasks (factory + Lambda)
    deferred_task_provider: str
    aws_deferred_transport: str
    aws_sqs_queue_url: str
    aws_lambda_function_name: str
    eventbridge_scheduler_enabled_raw: str
    eventbridge_role_arn: str
    eventbridge_lambda_arn: str
    eventbridge_scheduler_group: str
    aws_region: str
    aws_account_id: str

    # Default file storage interface (create_default_storage)
    file_interface: str


def _load_env_impl() -> EnvConfig:
    max_pool = os.getenv("JVSPATIAL_MONGODB_MAX_POOL_SIZE")
    min_pool = os.getenv("JVSPATIAL_MONGODB_MIN_POOL_SIZE")
    environment = os.getenv("JVAGENT_ENVIRONMENT") or os.getenv("JVSPATIAL_ENVIRONMENT")
    serverless = is_serverless_mode()
    work_claim_raw = os.getenv("JVSPATIAL_WORK_CLAIM_STALE_SECONDS", "600")
    try:
        work_claim_stale_seconds = float(work_claim_raw)
    except ValueError:
        work_claim_stale_seconds = 600.0
    deferred_invoke_disabled_flag = _parse_bool_on(
        os.getenv("JVSPATIAL_DEFERRED_INVOKE_DISABLED", "")
    )
    deferred_invoke_secret_raw = os.getenv(
        "JVSPATIAL_DEFERRED_INVOKE_SECRET", ""
    ).strip()
    deferred_invoke_secret_val = (
        deferred_invoke_secret_raw if deferred_invoke_secret_raw else None
    )
    default_jsondb_path = "/tmp/jvdb" if serverless else "jvdb"
    default_sqlite_path = (
        "/tmp/jvdb/sqlite/jvspatial.db" if serverless else "jvdb/sqlite/jvspatial.db"
    )
    sqlite_explicit = os.getenv("JVSPATIAL_SQLITE_PATH", "").strip()
    db_path_raw = os.getenv("JVSPATIAL_DB_PATH", "").strip()
    resolved_db_path = sqlite_explicit or db_path_raw or default_sqlite_path

    cors_origins = _split_csv_list(os.getenv("JVSPATIAL_CORS_ORIGINS"))
    if cors_origins is None:
        cors_origins = list(_DEFAULT_DEV_CORS_ORIGINS)
    cors_methods = _split_csv_list(os.getenv("JVSPATIAL_CORS_METHODS")) or ["*"]
    cors_headers = _split_csv_list(os.getenv("JVSPATIAL_CORS_HEADERS")) or ["*"]

    s3_region = (
        os.getenv("JVSPATIAL_S3_REGION_NAME", "").strip()
        or os.getenv("JVSPATIAL_S3_REGION", "").strip()
        or "us-east-1"
    )
    s3_key = (
        os.getenv("JVSPATIAL_S3_ACCESS_KEY_ID", "").strip()
        or os.getenv("JVSPATIAL_S3_ACCESS_KEY", "").strip()
    )
    s3_secret = (
        os.getenv("JVSPATIAL_S3_SECRET_ACCESS_KEY", "").strip()
        or os.getenv("JVSPATIAL_S3_SECRET_KEY", "").strip()
    )
    s3_key_final = s3_key or None
    s3_secret_final = s3_secret or None

    log_db_region = os.getenv("JVSPATIAL_LOG_DB_REGION", "").strip() or None
    log_db_endpoint = os.getenv("JVSPATIAL_LOG_DB_ENDPOINT_URL", "").strip() or None
    log_db_uri = os.getenv("JVSPATIAL_LOG_DB_URI", "").strip() or None

    redis_url_raw = os.getenv("JVSPATIAL_REDIS_URL", "").strip()
    redis_url = redis_url_raw or None

    log_db_path_raw = os.getenv("JVSPATIAL_LOG_DB_PATH", "").strip()
    log_db_path_json_val = log_db_path_raw or "./jvspatial_logs"
    log_db_path_sqlite_val = (
        log_db_path_raw or "jvspatial_logs/sqlite/jvspatial_logs.db"
    )

    return EnvConfig(
        db_type=os.getenv("JVSPATIAL_DB_TYPE", "json"),
        jsondb_path=os.getenv("JVSPATIAL_JSONDB_PATH", default_jsondb_path),
        db_path=resolved_db_path,
        mongodb_uri=os.getenv("JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017"),
        mongodb_db_name=os.getenv("JVSPATIAL_MONGODB_DB_NAME", "jvdb"),
        mongodb_max_pool=int(max_pool) if max_pool else None,
        mongodb_min_pool=int(min_pool) if min_pool else None,
        dynamodb_table_name=os.getenv("JVSPATIAL_DYNAMODB_TABLE_NAME", "jvspatial"),
        dynamodb_region=os.getenv("JVSPATIAL_DYNAMODB_REGION", "us-east-1"),
        dynamodb_endpoint_url=os.getenv("JVSPATIAL_DYNAMODB_ENDPOINT_URL"),
        dynamodb_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        dynamodb_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        dynamodb_wait_for_index=_parse_bool(
            os.getenv("JVSPATIAL_DYNAMODB_WAIT_FOR_INDEX", "false")
        ),
        webhook_hmac_secret=os.getenv("JVSPATIAL_WEBHOOK_HMAC_SECRET"),
        webhook_hmac_algorithm=os.getenv("JVSPATIAL_WEBHOOK_HMAC_ALGORITHM", "sha256"),
        webhook_max_payload_size=int(
            os.getenv("JVSPATIAL_WEBHOOK_MAX_PAYLOAD_SIZE", "1048576")
        ),
        webhook_idempotency_ttl=int(
            os.getenv("JVSPATIAL_WEBHOOK_IDEMPOTENCY_TTL", "3600")
        ),
        webhook_https_required=_parse_bool(
            os.getenv("JVSPATIAL_WEBHOOK_HTTPS_REQUIRED", "true")
        ),
        walker_max_steps=int(os.getenv("JVSPATIAL_WALKER_MAX_STEPS", "10000")),
        walker_max_visits_per_node=int(
            os.getenv("JVSPATIAL_WALKER_MAX_VISITS_PER_NODE", "100")
        ),
        walker_max_execution_time=float(
            os.getenv("JVSPATIAL_WALKER_MAX_EXECUTION_TIME", "300.0")
        ),
        walker_max_queue_size=int(os.getenv("JVSPATIAL_WALKER_MAX_QUEUE_SIZE", "1000")),
        walker_protection_enabled=_parse_bool(
            os.getenv("JVSPATIAL_WALKER_PROTECTION_ENABLED", "true")
        ),
        auto_create_indexes=_parse_bool(
            os.getenv("JVSPATIAL_AUTO_CREATE_INDEXES", "false")
        ),
        text_normalization_enabled=_parse_bool(
            os.getenv("JVSPATIAL_TEXT_NORMALIZATION_ENABLED", "true")
        ),
        s3_bucket_name=os.getenv("JVSPATIAL_S3_BUCKET_NAME"),
        s3_region_name=s3_region,
        s3_access_key_id=s3_key_final or None,
        s3_secret_access_key=s3_secret_final or None,
        s3_endpoint_url=os.getenv("JVSPATIAL_S3_ENDPOINT_URL"),
        environment=environment,
        serverless_mode=serverless,
        work_claim_stale_seconds=work_claim_stale_seconds,
        deferred_invoke_disabled=deferred_invoke_disabled_flag,
        deferred_invoke_secret=deferred_invoke_secret_val,
        api_prefix=os.getenv("JVSPATIAL_API_PREFIX", "/api"),
        api_health=os.getenv("JVSPATIAL_API_HEALTH", "/health"),
        api_root=os.getenv("JVSPATIAL_API_ROOT", "/"),
        storage_prefix=os.getenv("JVSPATIAL_STORAGE_PREFIX", "/storage"),
        proxy_prefix=os.getenv("JVSPATIAL_PROXY_PREFIX", "/p"),
        collection_users=os.getenv("JVSPATIAL_COLLECTION_USERS", "users"),
        collection_api_keys=os.getenv("JVSPATIAL_COLLECTION_API_KEYS", "api_keys"),
        collection_sessions=os.getenv("JVSPATIAL_COLLECTION_SESSIONS", "sessions"),
        collection_webhooks=os.getenv("JVSPATIAL_COLLECTION_WEBHOOKS", "webhooks"),
        collection_webhook_requests=os.getenv(
            "JVSPATIAL_COLLECTION_WEBHOOK_REQUESTS", "webhook_requests"
        ),
        collection_scheduled_tasks=os.getenv(
            "JVSPATIAL_COLLECTION_SCHEDULED_TASKS", "scheduled_tasks"
        ),
        api_title=os.getenv("JVSPATIAL_API_TITLE", "jvspatial API"),
        api_version=os.getenv("JVSPATIAL_API_VERSION", "1.0.0"),
        api_description=os.getenv(
            "JVSPATIAL_API_DESCRIPTION", "API built with jvspatial framework"
        ),
        host=os.getenv("JVSPATIAL_HOST", "0.0.0.0"),
        port=int(os.getenv("JVSPATIAL_PORT", "8000")),
        log_level=os.getenv("JVSPATIAL_LOG_LEVEL", "info"),
        debug=_parse_bool(os.getenv("JVSPATIAL_DEBUG", "false")),
        cors_enabled=_parse_bool(os.getenv("JVSPATIAL_CORS_ENABLED", "true")),
        cors_origins=cors_origins,
        cors_methods=cors_methods,
        cors_headers=cors_headers,
        file_storage_enabled=_parse_bool(
            os.getenv("JVSPATIAL_FILE_STORAGE_ENABLED", "false")
        ),
        file_storage_provider=os.getenv("JVSPATIAL_FILE_STORAGE_PROVIDER", "local"),
        file_storage_root=resolve_file_storage_root(serverless=serverless),
        file_storage_max_size=int(
            os.getenv("JVSPATIAL_FILE_STORAGE_MAX_SIZE", str(100 * 1024 * 1024))
        ),
        file_storage_base_url=os.getenv(
            "JVSPATIAL_FILE_STORAGE_BASE_URL", "http://localhost:8000"
        ),
        proxy_enabled=_parse_bool(os.getenv("JVSPATIAL_PROXY_ENABLED", "false")),
        proxy_expiration=int(os.getenv("JVSPATIAL_PROXY_EXPIRATION", "3600")),
        proxy_max_expiration=int(os.getenv("JVSPATIAL_PROXY_MAX_EXPIRATION", "86400")),
        db_logging_enabled=_parse_bool(
            os.getenv("JVSPATIAL_DB_LOGGING_ENABLED", "true")
        ),
        db_logging_levels=os.getenv("JVSPATIAL_DB_LOGGING_LEVELS", "ERROR,CRITICAL"),
        db_logging_db_name=os.getenv("JVSPATIAL_DB_LOGGING_DB_NAME", "logs"),
        db_logging_api_enabled=_parse_bool(
            os.getenv("JVSPATIAL_DB_LOGGING_API_ENABLED", "true")
        ),
        log_db_type=os.getenv("JVSPATIAL_LOG_DB_TYPE", "").strip() or None,
        log_db_path_json=log_db_path_json_val,
        log_db_path_sqlite=log_db_path_sqlite_val,
        log_db_name=os.getenv("JVSPATIAL_LOG_DB_NAME", "jvspatial_logs"),
        log_db_table_name=os.getenv("JVSPATIAL_LOG_DB_TABLE_NAME", "jvspatial_logs"),
        log_db_uri=log_db_uri,
        log_db_region=log_db_region,
        log_db_endpoint_url=log_db_endpoint,
        cache_backend=os.getenv("JVSPATIAL_CACHE_BACKEND", "memory"),
        cache_size=int(os.getenv("JVSPATIAL_CACHE_SIZE", "1000")),
        redis_url=redis_url,
        redis_ttl=int(os.getenv("JVSPATIAL_REDIS_TTL", "3600")),
        l1_cache_size=int(os.getenv("JVSPATIAL_L1_CACHE_SIZE", "500")),
        auth_strict_hashing=_parse_bool_on(
            os.getenv("JVSPATIAL_AUTH_STRICT_HASHING", "")
        ),
        bcrypt_rounds=int(os.getenv("JVSPATIAL_BCRYPT_ROUNDS", "12")),
        bcrypt_rounds_serverless=int(
            os.getenv("JVSPATIAL_BCRYPT_ROUNDS_SERVERLESS", "10")
        ),
        argon2_time_cost=int(os.getenv("JVSPATIAL_ARGON2_TIME_COST", "2")),
        argon2_memory_cost=int(os.getenv("JVSPATIAL_ARGON2_MEMORY_COST", "19456")),
        argon2_parallelism=int(os.getenv("JVSPATIAL_ARGON2_PARALLELISM", "2")),
        enable_deferred_saves=os.getenv("JVSPATIAL_ENABLE_DEFERRED_SAVES", "true")
        .strip()
        .lower()
        == "true",
        deferred_task_provider=os.getenv(
            "JVSPATIAL_DEFERRED_TASK_PROVIDER", ""
        ).strip(),
        aws_deferred_transport=os.getenv(
            "JVSPATIAL_AWS_DEFERRED_TRANSPORT", ""
        ).strip(),
        aws_sqs_queue_url=os.getenv("JVSPATIAL_AWS_SQS_QUEUE_URL", "").strip(),
        aws_lambda_function_name=os.getenv("AWS_LAMBDA_FUNCTION_NAME", "").strip(),
        eventbridge_scheduler_enabled_raw=os.getenv(
            "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED", ""
        ),
        eventbridge_role_arn=os.getenv("JVSPATIAL_EVENTBRIDGE_ROLE_ARN", "").strip(),
        eventbridge_lambda_arn=os.getenv(
            "JVSPATIAL_EVENTBRIDGE_LAMBDA_ARN", ""
        ).strip(),
        eventbridge_scheduler_group=os.getenv(
            "JVSPATIAL_EVENTBRIDGE_SCHEDULER_GROUP", "default"
        ).strip()
        or "default",
        aws_region=os.getenv("AWS_REGION", "us-east-1").strip() or "us-east-1",
        aws_account_id=os.getenv("AWS_ACCOUNT_ID", "").strip(),
        file_interface=os.getenv("JVSPATIAL_FILE_INTERFACE", "local").strip()
        or "local",
    )


@functools.lru_cache(maxsize=1)
def load_env() -> EnvConfig:
    """Load all environment variables into a single :class:`EnvConfig` (cached)."""
    cfg = _load_env_impl()
    # Earliest hook: set LWA pass-through default before most code reads os.environ,
    # so deferred Lambda self-invoke works without IaC setting AWS_LWA_PASS_THROUGH_PATH.
    from jvspatial.runtime.lwa import apply_aws_lwa_env_defaults

    apply_aws_lwa_env_defaults(None)
    return cfg


def clear_load_env_cache() -> None:
    """Clear the :func:`load_env` cache (for tests or after changing ``os.environ``)."""
    load_env.cache_clear()


EnvironmentMode = Literal["development", "production"]


def get_environment_mode(
    config_fallback: Optional[Callable[[], Optional[str]]] = None,
) -> EnvironmentMode:
    """Get the current environment mode.

    Priority: env var (JVAGENT_ENVIRONMENT or JVSPATIAL_ENVIRONMENT) > config_fallback > default "development".

    Env vars are read from ``os.environ`` on each call (not from the
    :func:`load_env` cache) so mode tracks in-process changes and tests that
    mutate ``os.environ`` without clearing the cache.

    Args:
        config_fallback: Optional callable returning 'production' or 'development' from app config (e.g. app.yaml).

    Returns:
        'production' or 'development'
    """
    raw = os.getenv("JVAGENT_ENVIRONMENT") or os.getenv("JVSPATIAL_ENVIRONMENT")
    if raw is not None and str(raw).strip():
        mode = str(raw).strip().lower()
        return "production" if mode == "production" else "development"
    if config_fallback is not None:
        config_value = config_fallback()
        if config_value is not None:
            return (
                "production" if config_value.lower() == "production" else "development"
            )
    return "development"


def is_development_mode(
    config_fallback: Optional[Callable[[], Optional[str]]] = None,
) -> bool:
    """Check if running in development mode."""
    return get_environment_mode(config_fallback) == "development"


def is_production_mode(
    config_fallback: Optional[Callable[[], Optional[str]]] = None,
) -> bool:
    """Check if running in production mode."""
    return get_environment_mode(config_fallback) == "production"
