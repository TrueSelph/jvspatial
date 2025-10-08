"""Configuration models for the jvspatial Server.

This module provides configuration models for server setup, including
database, CORS, file storage, and other server-related settings.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


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
        cors_enabled: Enable CORS middleware
        cors_origins: Allowed CORS origins
        cors_methods: Allowed CORS methods
        cors_headers: Allowed CORS headers
        db_type: Database type override
        db_path: Database path override
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

    # CORS Configuration
    cors_enabled: bool = True
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])
    cors_methods: List[str] = Field(default_factory=lambda: ["*"])
    cors_headers: List[str] = Field(default_factory=lambda: ["*"])

    # Database Configuration
    db_type: Optional[str] = None
    db_path: Optional[str] = None
    db_connection_string: Optional[str] = None
    db_database_name: Optional[str] = None

    # Logging Configuration
    log_level: str = "info"

    # Lifecycle Hooks
    startup_hooks: List[str] = Field(default_factory=list)
    shutdown_hooks: List[str] = Field(default_factory=list)

    # File Storage Configuration
    file_storage_enabled: bool = Field(
        default=False, validation_alias="JVSPATIAL_FILE_STORAGE_ENABLED"
    )
    file_storage_provider: str = Field(
        default="local", validation_alias="JVSPATIAL_FILE_STORAGE_PROVIDER"
    )  # "local" or "s3"
    file_storage_root: str = Field(
        default=".files", validation_alias="JVSPATIAL_FILE_STORAGE_ROOT"
    )
    file_storage_base_url: str = Field(
        default="http://localhost:8000",
        validation_alias="JVSPATIAL_FILE_STORAGE_BASE_URL",
    )
    file_storage_max_size: int = Field(
        default=100 * 1024 * 1024, validation_alias="JVSPATIAL_FILE_STORAGE_MAX_SIZE"
    )  # 100MB default

    # S3 Configuration (only used if provider is "s3")
    s3_bucket_name: Optional[str] = Field(
        default=None, validation_alias="JVSPATIAL_S3_BUCKET_NAME"
    )
    s3_region: Optional[str] = Field(
        default=None, validation_alias="JVSPATIAL_S3_REGION"
    )
    s3_access_key: Optional[str] = Field(
        default=None, validation_alias="JVSPATIAL_S3_ACCESS_KEY"
    )
    s3_secret_key: Optional[str] = Field(
        default=None, validation_alias="JVSPATIAL_S3_SECRET_KEY"
    )
    s3_endpoint_url: Optional[str] = Field(
        default=None, validation_alias="JVSPATIAL_S3_ENDPOINT_URL"
    )

    # URL Proxy Configuration
    proxy_enabled: bool = Field(
        default=False, validation_alias="JVSPATIAL_PROXY_ENABLED"
    )
    proxy_default_expiration: int = Field(
        default=3600, validation_alias="JVSPATIAL_PROXY_DEFAULT_EXPIRATION"
    )  # 1 hour
    proxy_max_expiration: int = Field(
        default=86400, validation_alias="JVSPATIAL_PROXY_MAX_EXPIRATION"
    )  # 24 hours
