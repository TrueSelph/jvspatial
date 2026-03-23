"""FastAPI app construction for :class:`~jvspatial.api.server.Server`."""

from __future__ import annotations

from fastapi import FastAPI

from jvspatial.api.constants import APIRoutes
from jvspatial.api.server_configurator import ServerConfigurator


class ServerAppFactoryMixin:
    """Build and cache the ASGI application instance."""

    def _rebuild_app_if_needed(self) -> None:
        """Rebuild the FastAPI app to reflect dynamic changes.

        This is necessary because FastAPI doesn't support removing routes/routers
        at runtime, so we need to recreate the entire app.
        """
        if not self._is_running or self.app is None:
            return

        try:
            self._logger.info(
                "🔄 Rebuilding FastAPI app for dynamic endpoint changes..."
            )

            self.app = self._create_app_instance()

            self._logger.warning(
                "App rebuilt internally. For changes to take effect in a running server, "
                "you may need to restart or use a development server with reload=True"
            )

        except Exception as e:
            self._logger.error(f"❌ Failed to rebuild app: {e}")

    def _create_app_instance(self) -> FastAPI:
        """Create FastAPI instance using the focused AppBuilder component.

        Returns:
            FastAPI: Fully configured application instance
        """
        lifespan = self.lifecycle_manager.lifespan if not self._is_running else None
        app = self.app_builder.create_app(lifespan=lifespan)

        self.middleware_manager.configure_all(app)

        ServerConfigurator(self).configure_all(app)

        self.app_builder.register_core_routes(app, self._graph_context, server=self)

        from jvspatial.api.decorators.deferred_registry import sync_endpoint_modules

        synced = sync_endpoint_modules(self)
        if synced > 0:
            self._logger.info(f"Synced {synced} endpoint(s) from module tracker")

        if self.discovery_service.enabled and not self._is_running:
            try:
                discovered_count = self.discovery_service.discover_and_register()
                if discovered_count > 0:
                    self._logger.info(f"🔍 Endpoints: {discovered_count} discovered")
            except Exception as e:
                self._logger.warning(f"⚠️ Endpoint discovery failed: {e}")

        self._include_routers(app)

        if self._auth_endpoints_registered and hasattr(self, "_auth_router"):
            app.include_router(self._auth_router, prefix=APIRoutes.PREFIX)

        self.app_builder.configure_openapi_security(app, self._has_auth_endpoints)

        return app

    def _include_routers(self, app: FastAPI) -> None:
        """Include endpoint routers and dynamic routers.

        Args:
            app: FastAPI application instance to configure
        """
        app.include_router(self.endpoint_router.router, prefix=APIRoutes.PREFIX)

        for endpoint_info in self._endpoint_registry.get_dynamic_endpoints():
            if endpoint_info.router:
                app.include_router(endpoint_info.router.router, prefix=APIRoutes.PREFIX)

    def _create_app(self) -> FastAPI:
        """Create and configure the FastAPI application."""
        return self._create_app_instance()

    def get_app(self) -> FastAPI:
        """Get the FastAPI application instance.

        Returns:
            Configured FastAPI application
        """
        if self.app is None:
            self.app = self._create_app()
        return self.app
