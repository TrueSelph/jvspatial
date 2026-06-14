"""Configuration models for the jvspatial Server.

This module provides configuration models for server setup, including
database, CORS, file storage, and other server-related settings.
"""

from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config_groups import (
    AuthConfig,
    CORSConfig,
    DatabaseConfig,
    FileStorageConfig,
    ProxyConfig,
    RateLimitConfig,
    SecurityConfig,
    WebhookConfig,
)
from .middleware.rate_limit_backend import RateLimitBackend


class ServerConfig(BaseModel):
    """Configuration model for the jvspatial Server.

    Attributes:
        title: API title
        description: API description
        version: API version
        debug: Enable debug mode
        host: Server host address
        port: Server port number
        docs_url: OpenAPI documentation URL
        redoc_url: ReDoc documentation URL
        database: Database configuration group
        cors: CORS configuration group
        auth: Authentication configuration group
        rate_limit: Rate limiting configuration group
        file_storage: File storage configuration group
        webhook: Webhook configuration group
        proxy: Proxy configuration group
        log_level: Logging level
        rate_limit_backend: Optional shared rate-limit storage backend
        startup_hooks: List of startup hook function names
        shutdown_hooks: List of shutdown hook function names
    """

    # ``rate_limit_backend`` holds a runtime ``RateLimitBackend`` instance, which
    # is a Protocol — pydantic cannot validate it as a model, so allow arbitrary
    # types for this field.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # API Configuration
    title: str = "jvspatial API"
    description: str = "API built with jvspatial framework"
    version: str = "1.0.0"
    debug: bool = False

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    docs_url: Optional[str] = "/docs"
    redoc_url: Optional[str] = "/redoc"
    serverless_mode: Optional[bool] = None
    deferred_task_provider: Optional[str] = None
    scheduler_enabled: bool = False
    scheduler_interval: int = 1

    # Configuration Groups (using composition)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    cors: CORSConfig = Field(default_factory=CORSConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    file_storage: FileStorageConfig = Field(default_factory=FileStorageConfig)

    # Pluggable rate-limit storage backend. ``None`` (default) means the
    # middleware falls back to a process-local ``MemoryRateLimitBackend`` —
    # behaviour unchanged from before this field existed.
    #
    # **Multi-worker limitation.** The in-memory backend's counter is
    # per-process, so under ``N`` workers (gunicorn workers, concurrent Lambda
    # invocations) the *effective* cap is ``N × configured`` — each worker
    # tracks its own bucket. This applies to ALL caps, including the
    # unauthenticated DCR ``/oauth/register`` limit wired by
    # ``AuthConfigurator._wire_dcr_rate_limit``. For a hard global cap, supply a
    # shared backend (e.g. ``RedisRateLimitBackend``) here so every worker
    # increments the same counter.
    rate_limit_backend: Optional[RateLimitBackend] = Field(
        default=None,
        description=(
            "Shared rate-limit storage backend (RateLimitBackend). None falls "
            "back to a process-local MemoryRateLimitBackend; supply a "
            "RedisRateLimitBackend for a hard cap across multiple workers."
        ),
    )
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)

    # Logging Configuration
    log_level: str = "info"

    # Lifecycle Hooks
    startup_hooks: List[str] = Field(default_factory=list)
    shutdown_hooks: List[str] = Field(default_factory=list)

    # Graph Visualization Endpoint Configuration
    graph_endpoint_enabled: bool = Field(
        default=True,
        description=(
            "Enable graph visualization: /api/graph (DOT) plus /api/graph/expand "
            "and /api/graph/subgraph (JSON) when the server registers them"
        ),
    )

    @field_validator("port")
    @classmethod
    def _validate_port(cls, v: int) -> int:
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("host")
    @classmethod
    def _validate_host(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("Host cannot be empty")
        return v

    @model_validator(mode="before")
    @classmethod
    def _map_flat_db_config(cls, data: Any) -> Any:
        """Map flat db_type/db_path kwargs into database config for Server(**kwargs)."""
        if not isinstance(data, dict):
            return data
        db_type = data.get("db_type")
        db_path = data.get("db_path")
        db_path_resolve = data.get("db_path_resolve")
        if db_type is None and db_path is None and db_path_resolve is None:
            return data
        result = {
            k: v
            for k, v in data.items()
            if k not in ("db_type", "db_path", "db_path_resolve")
        }
        db = result.get("database") or {}
        if isinstance(db, dict):
            if db_type is not None:
                db = {**db, "db_type": db_type}
            if db_path is not None:
                db = {**db, "db_path": db_path}
            if db_path_resolve is not None:
                db = {**db, "db_path_resolve": db_path_resolve}
            result["database"] = db
        return result
