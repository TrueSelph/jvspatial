"""Configuration models for the jvspatial Server.

This module provides configuration models for server setup, including
database, CORS, file storage, and other server-related settings.
"""

from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator

from .config_groups import (
    AuthConfig,
    CORSConfig,
    DatabaseConfig,
    FileStorageConfig,
    ProxyConfig,
    RateLimitConfig,
    WebhookConfig,
)


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
        startup_hooks: List of startup hook function names
        shutdown_hooks: List of shutdown hook function names
    """

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

    # Configuration Groups (using composition)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    cors: CORSConfig = Field(default_factory=CORSConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    file_storage: FileStorageConfig = Field(default_factory=FileStorageConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)

    # Logging Configuration
    log_level: str = "info"

    # Lifecycle Hooks
    startup_hooks: List[str] = Field(default_factory=list)
    shutdown_hooks: List[str] = Field(default_factory=list)

    # Graph Visualization Endpoint Configuration
    graph_endpoint_enabled: bool = Field(
        default=True, description="Enable /api/graph endpoint for graph visualization"
    )

    @model_validator(mode="before")
    @classmethod
    def _map_flat_db_config(cls, data: Any) -> Any:
        """Map flat db_type/db_path kwargs into database config for Server(**kwargs)."""
        if not isinstance(data, dict):
            return data
        db_type = data.get("db_type")
        db_path = data.get("db_path")
        if db_type is None and db_path is None:
            return data
        result = {k: v for k, v in data.items() if k not in ("db_type", "db_path")}
        db = result.get("database") or {}
        if isinstance(db, dict):
            if db_type is not None:
                db = {**db, "db_type": db_type}
            if db_path is not None:
                db = {**db, "db_path": db_path}
            result["database"] = db
        return result
