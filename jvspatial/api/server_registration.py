"""Dynamic endpoint registration, auth route toggles, and discovery for Server."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Type, Union, cast

from jvspatial.api.constants import APIRoutes
from jvspatial.api.endpoints.router import EndpointRouter
from jvspatial.core.entities import Walker


class ServerRegistrationMixin:
    """Walker/function endpoint registration and package discovery."""

    def disable_auth_endpoint(self, path: str) -> bool:
        """Disable a specific auth endpoint by removing it from the auth router.

        This method removes routes from the auth router before it's included in the app.
        The path can be either:
        - Relative to router prefix: "/register" (recommended)
        - Full path including router prefix: "/auth/register"

        The endpoint will be accessible at "/api/auth/register" when the router
        is included with the API prefix.

        Args:
            path: Path to disable, either relative ("/register") or full ("/auth/register")

        Returns:
            True if endpoint was found and removed, False otherwise
        """
        if not hasattr(self, "_auth_router") or self._auth_router is None:
            self._logger.debug(
                f"Auth router not available, cannot disable endpoint: {path}"
            )
            return False

        if not path.startswith("/"):
            path = f"/{path}"

        if path.startswith("/auth/"):
            full_path = path
            relative_path = path[6:]
        elif path.startswith("/auth"):
            full_path = "/auth"
            relative_path = "/"
        else:
            full_path = f"/auth{path}"
            relative_path = path

        from fastapi.routing import APIRoute

        routes_to_remove = []
        available_paths = []

        normalized_full_path = full_path.rstrip("/")
        normalized_relative_path = relative_path.rstrip("/")

        for route in self._auth_router.routes:
            if isinstance(route, APIRoute):
                route_path = route.path
                if route_path:
                    available_paths.append(route_path)
                    normalized_route_path = route_path.rstrip("/")
                    normalized_full = normalized_full_path
                    normalized_rel = normalized_relative_path

                    if normalized_route_path in (normalized_full, normalized_rel):
                        routes_to_remove.append(route)

        if routes_to_remove:
            for route in routes_to_remove:
                self._auth_router.routes.remove(route)
                route_path = route.path if isinstance(route, APIRoute) else None
                self._logger.info(
                    f"🔒 Disabled auth endpoint: {route_path or full_path}"
                )
            return True
        else:
            if available_paths:
                self._logger.warning(
                    f"Could not find {full_path} endpoint to disable. "
                    f"Available auth endpoints: {', '.join(available_paths)}. "
                    f"The endpoint may have already been disabled or removed."
                )
            else:
                self._logger.warning(
                    f"Could not find {full_path} endpoint to disable. "
                    f"No auth endpoints found in router. "
                    f"Auth endpoints may not be registered yet."
                )
            return False

    def _register_walker_dynamically(
        self,
        walker_class: Type[Walker],
        path: str,
        methods: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Register a walker endpoint dynamically while server is running."""
        if self.app is None:
            return

        try:
            dynamic_router = EndpointRouter()
            dynamic_router.endpoint(path, methods, **kwargs)(walker_class)

            endpoint_info = self._endpoint_registry.get_walker_info(walker_class)
            if endpoint_info:
                endpoint_info.is_dynamic = True
                endpoint_info.router = dynamic_router
            self.app.include_router(dynamic_router.router, prefix=APIRoutes.PREFIX)

            for route in self.app.routes:
                if hasattr(route, "path") and path in route.path:
                    route_handler = route.endpoint
                    route_handler._auth_required = getattr(
                        walker_class, "_auth_required", False
                    )
                    route_handler._required_permissions = getattr(
                        walker_class, "_required_permissions", []
                    )
                    route_handler._required_roles = getattr(
                        walker_class, "_required_roles", []
                    )
                    break

            self._logger.info(
                f"🔄 Dynamically registered walker: {walker_class.__name__} at {path}"
            )

        except Exception as e:
            self._logger.error(
                f"❌ Failed to dynamically register walker {walker_class.__name__}: {e}"
            )

    def register_walker_class(
        self,
        walker_class: Type[Walker],
        path: str,
        methods: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Programmatically register a walker class."""
        if self._endpoint_registry.has_walker(walker_class):
            self._logger.warning(f"Walker {walker_class.__name__} already registered")
            return

        self._endpoint_registry.register_walker(
            walker_class,
            path,
            methods or ["POST"],
            router=self.endpoint_router,
            **kwargs,
        )

        if self._is_running and self.app is not None:
            self._register_walker_dynamically(walker_class, path, methods, **kwargs)
        else:
            walker_class._jvspatial_endpoint_config = {  # type: ignore[attr-defined]
                "path": path,
                "methods": methods or ["POST"],
                "kwargs": kwargs,
            }
            self.endpoint_router.endpoint(path, methods, **kwargs)(walker_class)

        self._logger.info(
            f"📝 Registered walker class: {walker_class.__name__} at {path}"
        )

    async def unregister_walker_class(self, walker_class: Type[Walker]) -> bool:
        """Remove a walker class and its endpoint from the server."""
        if not self._endpoint_registry.has_walker(walker_class):
            self._logger.warning(f"Walker {walker_class.__name__} not registered")
            return False

        try:
            success = self._endpoint_registry.unregister_walker(walker_class)

            if not success:
                return False

            if self._is_running:
                self._app_needs_rebuild = True
                self._rebuild_app_if_needed()
                self._logger.info(
                    f"🔄 FastAPI app rebuilt to remove walker endpoint: {walker_class.__name__}"
                )

            self._logger.info(f"🗑️ Unregistered walker class: {walker_class.__name__}")
            return True

        except Exception as e:
            self._logger.error(
                f"❌ Failed to unregister walker {walker_class.__name__}: {e}"
            )
            return False

    async def unregister_walker_endpoint(self, path: str) -> List[Type[Walker]]:
        """Remove all walkers registered to a specific path."""
        removed_walkers: List[Type[Walker]] = []

        endpoints = self._endpoint_registry.get_by_path(path)

        for endpoint_info in endpoints:
            if endpoint_info.endpoint_type.value == "walker":
                handler = endpoint_info.handler
                if isinstance(handler, type):
                    walker_class = cast(Type[Walker], handler)
                    if await self.unregister_walker_class(walker_class):
                        removed_walkers.append(walker_class)

        if removed_walkers:
            walker_names = [cls.__name__ for cls in removed_walkers]
            self._logger.info(
                f"🗑️ Removed {len(removed_walkers)} walkers from path {path}: {walker_names}"
            )

        return removed_walkers

    async def unregister_endpoint(self, endpoint: Union[str, Callable]) -> bool:
        """Remove a function endpoint from the server."""
        success = False
        if isinstance(endpoint, str):
            path = endpoint
            removed_count = self._endpoint_registry.unregister_by_path(path)

            if removed_count > 0:
                self._logger.info(
                    f"🗑️ Removed {removed_count} endpoints from path {path}"
                )
                success = True
            else:
                self._logger.warning(f"No endpoints found at path {path}")
                success = False

        elif callable(endpoint):
            func = endpoint

            if not self._endpoint_registry.has_function(func):
                self._logger.warning(f"Function {func.__name__} not registered")
                return False

            success = self._endpoint_registry.unregister_function(func)

            if success:
                self._logger.info(f"🗑️ Removed function endpoint: {func.__name__}")

        else:
            self._logger.error(
                "Invalid endpoint parameter: must be string path or callable function"
            )
            return False

        if success and self._is_running:
            self._app_needs_rebuild = True
            self._rebuild_app_if_needed()
            self._logger.info("🔄 FastAPI app rebuilt to remove function endpoint")

        return success

    async def unregister_endpoint_by_path(self, path: str) -> int:
        """Remove all endpoints (both walker and function) from a specific path."""
        removed_count = self._endpoint_registry.unregister_by_path(path)

        if removed_count > 0:
            self._logger.info(
                f"🗑️ Removed {removed_count} total endpoints from path {path}"
            )

        return removed_count

    async def list_function_endpoints(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all registered function endpoints."""
        return self._endpoint_registry.list_functions()

    def list_all_endpoints(self) -> Dict[str, Any]:
        """Get information about all registered endpoints (walkers and functions)."""
        return self._endpoint_registry.list_all()

    def list_walker_endpoints(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all registered walkers."""
        return self._endpoint_registry.list_walkers()

    def enable_package_discovery(
        self, enabled: bool = True, patterns: Optional[List[str]] = None
    ) -> None:
        """Enable or disable automatic package discovery."""
        self.discovery_service.enable(enabled, patterns)

    def refresh_endpoints(self) -> int:
        """Refresh and discover new endpoints from packages."""
        if not self._is_running:
            self._logger.warning("Cannot refresh endpoints - server is not running")
            return 0

        return self.discovery_service.discover_and_register()

    def endpoint(
        self, path: str, methods: Optional[List[str]] = None, **kwargs: Any
    ) -> Callable:
        """Endpoint decorator for the server instance."""
        return self.endpoint_manager.register_endpoint(path, methods, **kwargs)
