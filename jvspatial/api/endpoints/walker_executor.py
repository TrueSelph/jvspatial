"""Walker execution logic for endpoint handlers.

This module provides a unified execution path for walkers, eliminating
duplication between GET and POST handlers.
"""

from typing import Any, Dict, Optional, Protocol, runtime_checkable

from jvspatial.core.context import get_default_context
from jvspatial.core.entities import Node, Walker


@runtime_checkable
class DirectExecutionWalker(Protocol):
    """Protocol for walkers with direct execution methods (no graph traversal).

    Walkers implementing this protocol provide an `execute()` method that
    performs their logic directly without graph traversal.
    """

    async def execute(self) -> Dict[str, Any]:
        """Execute walker logic directly.

        Returns:
            Result dictionary from walker execution
        """
        ...


class WalkerExecutor:
    """Unified executor for walker endpoints.

    Handles both direct execution walkers (API-style) and traditional
    graph traversal walkers in a single, maintainable code path.
    """

    def __init__(self, router: Any):
        """Initialize the walker executor.

        Args:
            router: Router instance for error handling and response formatting
        """
        self.router = router

    async def execute_walker(
        self,
        walker: Walker,
        walker_cls: type[Walker],
        start_node: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a walker instance and return formatted result.

        Args:
            walker: Walker instance to execute
            walker_cls: Walker class (for metadata access)
            start_node: Optional start node ID for graph traversal

        Returns:
            Formatted response dictionary

        Raises:
            HTTPException: For various error conditions
        """
        # Check if walker implements direct execution protocol
        if isinstance(walker, DirectExecutionWalker) or (
            hasattr(walker, "execute") and callable(walker.execute)
        ):
            result = await walker.execute()
        else:
            # Traditional graph traversal walker
            result = await self._execute_traversal_walker(walker, start_node)

        # Check if response schema is defined
        has_response_schema = bool(
            getattr(walker_cls, "_jvspatial_endpoint_config", {}).get("response")
        )

        # Return result directly if schema defined, otherwise format it
        if has_response_schema:
            return result if isinstance(result, dict) else {"data": result}
        else:
            return self.router.format_response(data=result)

    async def _execute_traversal_walker(
        self, walker: Walker, start_node: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a traditional graph traversal walker.

        Args:
            walker: Walker instance
            start_node: Optional start node ID

        Returns:
            Merged response from walker reports

        Raises:
            HTTPException: For various error conditions
        """
        # Resolve start node
        if start_node:
            start = await get_default_context().get(Node, start_node)
            if not start:
                self.router.raise_error(404, f"Start node '{start_node}' not found")
        else:
            # Default to root node
            start = await get_default_context().get(Node, "n.Root.root")
            if not start:
                self.router.raise_error(
                    500,
                    "Root node not found - database may not be properly initialized",
                )

        # Execute walker
        result = await walker.spawn(start)

        # Process response
        reports = await result.get_report()
        if not reports:
            return self.router.format_response()

        # Merge reports and handle errors
        response = {}
        for report in reports:
            if not isinstance(report, dict):
                continue

            # Check for error reports
            status = report.get("status")
            error_msg = report.get("error") or report.get("detail")

            # Determine error status code
            if isinstance(status, int) and status >= 400:
                error_status = status
            elif error_msg:
                # Determine status from context
                if report.get("conflict"):
                    error_status = 409  # Conflict
                elif report.get("not_found"):
                    error_status = 404  # Not Found
                elif report.get("unauthorized"):
                    error_status = 401  # Unauthorized
                elif report.get("forbidden"):
                    error_status = 403  # Forbidden
                elif report.get("validation_error"):
                    error_status = 422  # Unprocessable Entity
                else:
                    error_status = 400  # Bad Request
            else:
                error_status = None

            # Raise error if this is an error report
            if error_status is not None:
                error_message = str(error_msg or "An error occurred")
                # Include additional details if available
                details = {
                    k: v
                    for k, v in report.items()
                    if k not in ("status", "error", "detail")
                }
                if details:
                    error_message += f" | Details: {details}"
                self.router.raise_error(error_status, error_message)

            response.update(report)

        return response


__all__ = ["WalkerExecutor", "DirectExecutionWalker"]
