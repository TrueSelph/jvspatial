"""Server class for FastAPI applications using jvspatial.

This module provides a high-level, object-oriented interface for creating
FastAPI servers with jvspatial integration, including automatic database
setup, lifecycle management, and endpoint routing.

"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Type, Union

from fastapi import FastAPI

from jvspatial.api.components import AppBuilder, EndpointManager
from jvspatial.api.components.error_handler import APIErrorHandler
from jvspatial.api.config import ServerConfig
from jvspatial.api.endpoints.router import EndpointRouter
from jvspatial.api.middleware.manager import MiddlewareManager
from jvspatial.api.server_app_factory import ServerAppFactoryMixin
from jvspatial.api.server_lifecycle import ServerLifecycleMixin
from jvspatial.api.server_registration import ServerRegistrationMixin
from jvspatial.api.server_run import ServerRunMixin
from jvspatial.api.services.discovery import EndpointDiscoveryService
from jvspatial.api.services.lifecycle import LifecycleManager
from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Node


class Server(
    ServerAppFactoryMixin,
    ServerRegistrationMixin,
    ServerLifecycleMixin,
    ServerRunMixin,
):
    """Base server class for FastAPI applications using jvspatial.

    This class provides core server functionality including:
    - FastAPI application creation and configuration
    - Database and file storage initialization
    - Endpoint registration and routing
    - Middleware and exception handling
    - Authentication setup
    - Lifecycle management

    Example:
        ```python
        from jvspatial.api.server import Server, endpoint
        from jvspatial.core.entities import Walker, Node, on_visit

        # Standard server
        server = Server(
            title="My Spatial API",
            description="A spatial data management API",
            db_type="json",
            db_path="./data"
        )

        @endpoint("/process")
        class ProcessData(Walker):
            data: str

            @on_visit(Node)
            async def process(self, here):
                self.response["processed"] = self.data.upper()

        if __name__ == "__main__":
            server.run()
        ```
    """

    def __init__(
        self,
        config: Optional[Union[ServerConfig, Dict[str, Any]]] = None,
        node_types: Optional[List[Type[Node]]] = None,
        on_startup: Optional[List[Callable]] = None,
        on_shutdown: Optional[List[Callable]] = None,
        on_admin_bootstrapped: Optional[Callable] = None,
        on_user_registered: Optional[Callable] = None,
        on_enrich_current_user: Optional[Callable] = None,
        on_password_reset_requested: Optional[Callable] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Server.

        Args:
            config: Server configuration as ServerConfig or dict
            node_types: Node subclasses to register with the server in bulk.
                Equivalent to calling ``server.add_node_type()`` for each class.
            on_startup: Async or sync callables added as startup lifecycle hooks.
            on_shutdown: Async or sync callables added as shutdown lifecycle hooks.
            on_admin_bootstrapped: Optional callback(user_response) called when bootstrap
                creates an admin. Use to create app-specific entities (e.g. UserNode).
            on_user_registered: Optional callback(user_response, request_body) called after
                registration. Use to create domain entities (e.g. UserNode, Organization).
            on_enrich_current_user: Optional callback(user_response) -> dict to augment
                /auth/me response. Return dict merged into the response.
            on_password_reset_requested: Optional callback(email, token, reset_url) called
                when a password reset is requested. Use to send reset email.
            **kwargs: Additional configuration parameters forwarded to ServerConfig
        """
        self._on_admin_bootstrapped = on_admin_bootstrapped
        self._on_user_registered = on_user_registered
        self._on_enrich_current_user = on_enrich_current_user
        self._on_password_reset_requested = on_password_reset_requested
        config_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k
            not in (
                "on_admin_bootstrapped",
                "on_user_registered",
                "on_enrich_current_user",
                "on_password_reset_requested",
            )
        }

        merged_config = self._merge_config(config, config_kwargs)

        self.config = ServerConfig(**merged_config)

        from jvspatial.runtime.lwa import (
            apply_aws_eventbridge_env_default,
            apply_aws_lwa_env_defaults,
        )

        apply_aws_eventbridge_env_default(self.config)
        apply_aws_lwa_env_defaults(self.config)

        self.app_builder = AppBuilder(self.config)
        self.endpoint_manager = EndpointManager()
        self.error_handler = APIErrorHandler()
        self.middleware_manager = MiddlewareManager(self)
        self.lifecycle_manager = LifecycleManager(self)
        self.discovery_service = EndpointDiscoveryService(self)

        self.app: Optional[FastAPI] = None
        self.endpoint_router = EndpointRouter()
        self._exception_handlers: Dict[Union[int, Type[Exception]], Callable] = {}
        self._logger = logging.getLogger(__name__)

        self._graph_context: Optional[GraphContext] = None

        self._file_interface: Optional[Any] = None
        self._proxy_manager: Optional[Any] = None
        self._file_storage_service: Optional[Any] = None

        self._endpoint_registry = self.endpoint_manager.get_registry()

        self._is_running = False
        self._dynamic_routes_registered = False
        self._app_needs_rebuild = False
        self._has_auth_endpoints = False
        self._custom_routes: List[Dict[str, Any]] = []

        self._auth_config: Optional[Any] = None
        self._auth_endpoints_registered = False
        self._auth_service: Optional[Any] = None

        if node_types:
            for node_cls in node_types:
                self.add_node_type(node_cls)

        if on_startup:
            for hook in on_startup:
                self.lifecycle_manager.add_startup_hook(hook)
        if on_shutdown:
            for hook in on_shutdown:
                self.lifecycle_manager.add_shutdown_hook(hook)

        from jvspatial.api.context import set_current_server

        set_current_server(self)

        from jvspatial.api.decorators.deferred_registry import flush_deferred_endpoints

        flushed_count = flush_deferred_endpoints(self)
        if flushed_count > 0:
            self._logger.debug(
                f"Registered {flushed_count} deferred endpoint(s) during server initialization"
            )

        if self.config.database.db_type:
            self._initialize_graph_context()

        self._configure_authentication()

        if self.config.file_storage.file_storage_enabled:
            self._initialize_file_storage()

    async def _bootstrap_admin_startup(self) -> None:
        """Create admin user on startup when bootstrap_admin_* config is set."""
        import os

        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"):
            return
        if not self._auth_service:
            return
        email = self.config.auth.bootstrap_admin_email
        password = self.config.auth.bootstrap_admin_password
        if not email or not password:
            return
        if len(password) < 6:
            self._logger.warning(
                "bootstrap_admin_password must be at least 6 characters; skipping bootstrap"
            )
            return
        try:
            name = self.config.auth.bootstrap_admin_name or email
            user = await self._auth_service.bootstrap_admin(
                email=email, password=password, name=name
            )
            if user:
                self._logger.info("Bootstrap admin created: %s", email)
                callback = getattr(self, "_on_admin_bootstrapped", None)
                if callback:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(user)
                        else:
                            callback(user)
                    except Exception as e:
                        self._logger.exception(
                            "on_admin_bootstrapped callback failed: %s", e
                        )
        except Exception as e:
            self._logger.exception("Failed to bootstrap admin: %s", e)

    def _configure_authentication(self) -> None:
        """Configure authentication middleware and register auth endpoints if enabled."""
        from jvspatial.api.components.auth_configurator import AuthConfigurator

        if (
            self.config.auth.auth_enabled
            and self.config.auth.jwt_secret
            == "your-secret-key"  # pragma: allowlist secret
        ):
            self._logger.warning(
                "⚠️  Using default JWT secret. Set jwt_secret in production!"
            )

        auth_configurator = AuthConfigurator(self.config, self._logger, server=self)
        self._auth_config = auth_configurator.configure()
        self._auth_router = auth_configurator.auth_router
        self._auth_endpoints_registered = auth_configurator.has_auth_endpoints
        self._has_auth_endpoints = auth_configurator.has_auth_endpoints
        self._auth_service = auth_configurator.auth_service

        if (
            self._auth_service
            and self.config.auth.bootstrap_admin_email
            and self.config.auth.bootstrap_admin_password
        ):
            self.lifecycle_manager.add_startup_hook(self._bootstrap_admin_startup)

    def _merge_config(self, config, kwargs) -> Dict[str, Any]:
        """Clean configuration merging.

        Args:
            config: Configuration object or dict
            kwargs: Additional configuration parameters

        Returns:
            Merged configuration dictionary
        """
        if config is None:
            return kwargs
        elif isinstance(config, ServerConfig):
            return {**config.model_dump(), **kwargs}
        else:
            return {**config, **kwargs}

    def _initialize_graph_context(self) -> None:
        """Initialize GraphContext with current database configuration."""
        from jvspatial.api.components.database_configurator import DatabaseConfigurator

        db_configurator = DatabaseConfigurator(self.config)
        self._graph_context = db_configurator.initialize_graph_context()

    def _initialize_file_storage(self) -> None:
        """Initialize file storage interface and proxy manager."""
        try:
            from jvspatial.api.services.file_storage import FileStorageService
            from jvspatial.storage import create_storage, get_proxy_manager

            if self.config.file_storage.file_storage_provider == "local":
                self._file_interface = create_storage(
                    provider="local",
                    root_dir=self.config.file_storage.file_storage_root,
                    base_url=self.config.file_storage.file_storage_base_url,
                    max_file_size=self.config.file_storage.file_storage_max_size,
                )
            elif self.config.file_storage.file_storage_provider == "s3":
                self._file_interface = create_storage(
                    provider="s3",
                    bucket_name=self.config.file_storage.s3_bucket_name,
                    region=self.config.file_storage.s3_region,
                    access_key=self.config.file_storage.s3_access_key,
                    secret_key=self.config.file_storage.s3_secret_key,
                    endpoint_url=self.config.file_storage.s3_endpoint_url,
                )
            else:
                raise ValueError(
                    f"Unsupported file storage provider: {self.config.file_storage.file_storage_provider}"
                )

            if self.config.proxy.proxy_enabled:
                self._proxy_manager = get_proxy_manager()

            self._file_storage_service = FileStorageService(
                file_interface=self._file_interface,
                proxy_manager=self._proxy_manager,
                config=self.config,
            )

            self._logger.info(
                f"📁 File storage initialized: {self.config.file_storage.file_storage_provider}"
            )

        except Exception as e:
            self._logger.error(f"❌ Failed to initialize file storage: {e}")
            raise

    def add_node_type(self, node_class: Type[Node]) -> None:
        """Register a Node type for use in walkers.

        Args:
            node_class: Node subclass to register
        """
        self._logger.info(f"Registered node type: {node_class.__name__}")

    def configure_database(self, db_type: str, **db_config: Any) -> None:
        """Configure database settings using GraphContext.

        Args:
            db_type: Database type ("json", "mongodb", etc.)
            **db_config: Database-specific configuration
        """
        self.config.database.db_type = db_type

        if db_type == "json" and "base_path" in db_config:
            self.config.database.db_path = db_config["base_path"]
        elif db_type == "mongodb":
            if "connection_string" in db_config:
                self.config.database.db_connection_string = db_config[
                    "connection_string"
                ]
            if "database_name" in db_config:
                self.config.database.db_database_name = db_config["database_name"]

        self._initialize_graph_context()

        self._logger.info(f"🗄️ Database configured with GraphContext: {db_type}")

    def get_graph_context(self) -> Optional[GraphContext]:
        """Get the GraphContext instance used by the server.

        Returns:
            GraphContext instance if configured, otherwise None (uses default GraphContext)
        """
        return self._graph_context

    def has_endpoint(self, path: str) -> bool:
        """Check if server has any endpoints at the given path.

        Args:
            path: URL path to check

        Returns:
            True if any endpoints exist at the path, False otherwise
        """
        return self._endpoint_registry.has_path(path)

    def set_graph_context(self, context: GraphContext) -> None:
        """Set a custom GraphContext for the server.

        Args:
            context: GraphContext instance to use
        """
        self._graph_context = context
        self._logger.info("🎯 Custom GraphContext set for server")


def create_server(
    title: str = "jvspatial API",
    description: str = "API built with jvspatial framework",
    version: str = "1.0.0",
    **config_kwargs: Any,
) -> Server:
    """Create a Server instance with common configuration.

    Args:
        title: API title
        description: API description
        version: API version
        **config_kwargs: Additional server configuration

    Returns:
        Configured Server instance
    """
    return Server(
        title=title, description=description, version=version, **config_kwargs
    )
