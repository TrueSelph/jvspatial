"""API module for defining FastAPI routes for walkers."""

from typing import Any, Callable, Dict, List, Optional, Type

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from jvspatial.core.entities import Walker


class GraphAPI:
    """API router for graph-based walkers."""

    def __init__(self: "GraphAPI") -> None:
        """Initialize the GraphAPI with an APIRouter."""
        self.router = APIRouter()

    def endpoint(
        self: "GraphAPI", path: str, methods: Optional[List[str]] = None, **kwargs: Any
    ) -> Callable[[Type[Walker]], Type[Walker]]:
        """Register a walker as an API endpoint."""
        """
        Args:
            path: The URL path for the endpoint
            methods: HTTP methods allowed (default: ["POST"])
            **kwargs: Additional arguments for route configuration
        """

        if methods is None:
            methods = ["POST"]

        def decorator(cls: Type[Walker]) -> Type[Walker]:
            async def handler(request: Dict[str, Any]) -> Dict[str, Any]:
                start_node = request.pop("start_node", None)

                try:
                    walker = cls(**request)
                except ValidationError as e:
                    raise HTTPException(status_code=422, detail=e.errors())

                result = await walker.spawn(start=start_node)

                if result.response:
                    if (
                        "status" in result.response
                        and isinstance(result.response["status"], int)
                        and result.response["status"] >= 400
                    ):
                        raise HTTPException(
                            status_code=result.response["status"],
                            detail=result.response.get("detail", "Unknown error"),
                        )
                    return result.response
                return {}

            self.router.add_api_route(
                path, handler, methods=methods, response_model=dict, **kwargs
            )
            return cls

        return decorator
