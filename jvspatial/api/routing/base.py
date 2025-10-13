"""Base router implementation for jvspatial API."""

from typing import Any, Callable, List, Optional, Protocol, TypeVar, runtime_checkable

from fastapi import APIRouter

T = TypeVar("T")


@runtime_checkable
class AuthEndpoint(Protocol):
    """Protocol for auth-aware endpoint functions."""

    _auth_required: bool
    _required_permissions: List[str]
    _required_roles: List[str]
    __call__: Callable[..., Any]


class BaseRouter:
    """Base router class with common functionality for all router types."""

    def __init__(self) -> None:
        """Initialize the router with an APIRouter."""
        self.router = APIRouter()

    def add_route(
        self,
        path: str,
        endpoint: Any,
        methods: Optional[List[str]] = None,
        source_obj: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Add a route to the router.

        Args:
            path: URL path for the endpoint
            endpoint: Endpoint handler function
            methods: HTTP methods (defaults to ["POST"])
            **kwargs: Additional FastAPI route parameters
        """
        if methods is None:
            methods = ["POST"]

        if source_obj and isinstance(source_obj, AuthEndpoint):
            # Propagate auth metadata to the endpoint function
            endpoint._auth_required = source_obj._auth_required  # type: ignore[attr-defined]
            endpoint._required_permissions = source_obj._required_permissions  # type: ignore[attr-defined]
            endpoint._required_roles = source_obj._required_roles  # type: ignore[attr-defined]

        self.router.add_api_route(
            path=path,
            endpoint=endpoint,
            methods=methods,
            **kwargs,
        )

    def include_router(self, router: APIRouter, **kwargs: Any) -> None:
        """Include another router.

        Args:
            router: Router to include
            **kwargs: Additional FastAPI include_router parameters
        """
        self.router.include_router(router, **kwargs)
