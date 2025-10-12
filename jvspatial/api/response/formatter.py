"""Response formatting utilities for jvspatial API."""

from typing import Any, Dict, Optional, Union

from .types import ErrorResponse, SuccessResponse


def format_response(
    data: Optional[Dict[str, Any]] = None,
    *,
    success: bool = True,
    message: Optional[str] = None,
    error: Optional[str] = None,
    detail: Optional[str] = None,
    code: Optional[str] = None,
    status: Optional[int] = None,
) -> Union[SuccessResponse, ErrorResponse]:
    """Format an API response.

    Args:
        data: Response data for successful responses
        success: Whether the request was successful
        message: Optional message for successful responses
        error: Error message for failed responses
        detail: Additional error details
        code: Error code
        status: HTTP status code for error responses

    Returns:
        Formatted API response
    """
    if success:
        return SuccessResponse(
            success=True,
            message=message,
            data=data or {},
        )
    else:
        return ErrorResponse(
            success=False,
            error=error or "Unknown error",
            detail=detail,
            code=code,
            status=status or 500,
        )
