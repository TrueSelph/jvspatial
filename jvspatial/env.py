"""Centralized environment variable loading for jvspatial.

All JVSPATIAL_* env vars are documented and loaded here. Modules should use
load_env() instead of os.getenv directly.

Single EnvConfig dataclass permits easy extensions with a common interface.
"""

import os
from dataclasses import dataclass
from typing import Callable, Literal, Optional


def _parse_bool(val: str) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes")


@dataclass
class EnvConfig:
    """Unified environment configuration. Single dataclass for all JVSPATIAL_* vars.

    Extend by adding new fields and populating them in load_env().
    """

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


def load_env() -> EnvConfig:
    """Load all environment variables into a single EnvConfig."""
    max_pool = os.getenv("JVSPATIAL_MONGODB_MAX_POOL_SIZE")
    min_pool = os.getenv("JVSPATIAL_MONGODB_MIN_POOL_SIZE")
    environment = os.getenv("JVAGENT_ENVIRONMENT") or os.getenv("JVSPATIAL_ENVIRONMENT")
    return EnvConfig(
        # Database
        db_type=os.getenv("JVSPATIAL_DB_TYPE", "json"),
        jsondb_path=os.getenv("JVSPATIAL_JSONDB_PATH", "jvdb"),
        db_path=os.getenv("JVSPATIAL_DB_PATH", "jvdb/sqlite/jvspatial.db"),
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
        # Webhook
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
        # Walker
        walker_max_steps=int(os.getenv("JVSPATIAL_WALKER_MAX_STEPS", "10000")),
        walker_max_visits_per_node=int(
            os.getenv("JVSPATIAL_WALKER_MAX_VISITS_PER_NODE", "100")
        ),
        walker_max_execution_time=float(
            os.getenv("JVSPATIAL_WALKER_MAX_EXECUTION_TIME", "300.0")
        ),
        walker_max_queue_size=int(os.getenv("JVSPATIAL_WALKER_MAX_QUEUE_SIZE", "1000")),
        # Core
        auto_create_indexes=_parse_bool(
            os.getenv("JVSPATIAL_AUTO_CREATE_INDEXES", "false")
        ),
        text_normalization_enabled=_parse_bool(
            os.getenv("JVSPATIAL_TEXT_NORMALIZATION_ENABLED", "true")
        ),
        # Storage (S3)
        s3_bucket_name=os.getenv("JVSPATIAL_S3_BUCKET_NAME"),
        s3_region_name=os.getenv("JVSPATIAL_S3_REGION_NAME", "us-east-1"),
        s3_access_key_id=os.getenv("JVSPATIAL_S3_ACCESS_KEY_ID"),
        s3_secret_access_key=os.getenv("JVSPATIAL_S3_SECRET_ACCESS_KEY"),
        s3_endpoint_url=os.getenv("JVSPATIAL_S3_ENDPOINT_URL"),
        # Environment mode
        environment=environment,
    )


EnvironmentMode = Literal["development", "production"]


def get_environment_mode(
    config_fallback: Optional[Callable[[], Optional[str]]] = None,
) -> EnvironmentMode:
    """Get the current environment mode.

    Priority: env var (JVAGENT_ENVIRONMENT or JVSPATIAL_ENVIRONMENT) > config_fallback > default "development".

    Args:
        config_fallback: Optional callable returning 'production' or 'development' from app config (e.g. app.yaml).

    Returns:
        'production' or 'development'
    """
    env = load_env()
    if env.environment is not None:
        mode = env.environment.lower()
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
