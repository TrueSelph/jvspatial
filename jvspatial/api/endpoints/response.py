"""Consolidated response handling for jvspatial API.

This module provides all response-related functionality including:
- Response type definitions (SuccessResponse, ErrorResponse)
- Response formatting utilities
- Response helper class with convenience methods
- Low-level response wrapper class
"""

from typing import Any, Dict, Optional, Union

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from jvspatial.core.entities import Walker

# ============================================================================
# Response Type Definitions
# ============================================================================


class APIResponse(BaseModel):
    """Base class for all API responses."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(description="Whether the request was successful")
    message: Optional[str] = Field(None, description="Human-readable message")


class SuccessResponse(APIResponse):
    """Successful API response with data."""

    success: bool = Field(True, description="Request was successful")
    data: Dict[str, Any] = Field(default_factory=dict, description="Response data")


class ErrorResponse(APIResponse):
    """Error API response with error details."""

    success: bool = Field(False, description="Request failed")
    error: str = Field(description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")
    code: Optional[str] = Field(None, description="Error code")
    status: int = Field(description="HTTP status code")


# ============================================================================
# Response Formatting Utilities
# ============================================================================


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
    """Format an API response using standard types.

    Args:
        data: Response data for successful responses
        success: Whether the request was successful
        message: Optional message for successful responses
        error: Error message for failed responses
        detail: Additional error details
        code: Error code
        status: HTTP status code for error responses

    Returns:
        Formatted API response (SuccessResponse or ErrorResponse)

    Example:
        >>> await format_response(data={"user": "john"}, success=True)
        SuccessResponse(success=True, data={"user": "john"})

        >>> await format_response(error="Not found", status=404, success=False)
        ErrorResponse(success=False, error="Not found", status=404)
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


# ============================================================================
# Low-Level Response Wrapper
# ============================================================================


class EndpointResponse:
    """Low-level response wrapper for jvspatial endpoints.

    This class provides a flexible interface for creating HTTP responses
    with configurable status codes, content, headers, and media types.
    Used internally by ResponseHelper and endpoint routers.

    Example:
        >>> resp = EndpointResponse(content={"data": "test"}, status_code=200)
        >>> resp.to_json_response()
        JSONResponse(content={"data": "test"}, status_code=200)
    """

    def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        media_type: str = "application/json",
    ) -> None:
        """Initialize EndpointResponse.

        Args:
            content: Response content/payload
            status_code: HTTP status code
            headers: Optional HTTP headers
            media_type: Response media type
        """
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.media_type = media_type

    async def to_json_response(self) -> JSONResponse:
        """Convert to FastAPI JSONResponse.

        Returns:
            JSONResponse object ready for FastAPI
        """
        return JSONResponse(
            content=self.content,
            status_code=self.status_code,
            headers=self.headers,
            media_type=self.media_type,
        )

    async def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for walker response property.

        Returns:
            Dictionary representation including status code
        """
        response_dict: Dict[str, Any] = {"status": self.status_code}
        if self.content is not None:
            if isinstance(self.content, dict):
                response_dict.update(self.content)
            else:
                response_dict["data"] = self.content
        if self.headers:
            response_dict["headers"] = self.headers
        return response_dict


# ============================================================================
# High-Level Response Helper
# ============================================================================


class ResponseHelper:
    """High-level helper class for generating API responses.

    This class provides convenient methods for creating common HTTP responses
    with appropriate status codes and formatting. Automatically handles both
    walker endpoints (returns dict) and function endpoints (returns JSONResponse).

    Example:
        >>> helper = ResponseHelper()
        >>> helper.success(data={"user": "john"})
        JSONResponse(content={"data": {"user": "john"}}, status_code=200)

        >>> helper.not_found(message="User not found")
        JSONResponse(content={"error": "User not found"}, status_code=404)
    """

    def __init__(self, *, walker_instance: Optional[Walker] = None) -> None:
        """Initialize the response helper.

        Args:
            walker_instance: Optional walker instance to update response property
        """
        self.walker_instance = walker_instance

    async def response(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        media_type: str = "application/json",
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create a flexible response.

        Args:
            content: Response content/payload
            status_code: HTTP status code
            headers: Optional HTTP headers
            media_type: Response media type

        Returns:
            JSONResponse for function endpoints, dict for walker endpoints
        """
        response_dict: Dict[str, Any] = {"status": status_code}
        if content is not None:
            if isinstance(content, dict):
                # Preserve status when updating with content
                content_copy = content.copy()
                response_dict.update(content_copy)
                response_dict["status"] = status_code
            else:
                response_dict["data"] = content
        if headers:
            response_dict["headers"] = headers

        if self.walker_instance is not None:
            # Set response property and add to report if available
            self.walker_instance.response = response_dict
            if hasattr(self.walker_instance, "report"):
                await self.walker_instance.report(response_dict)
            return response_dict
        else:
            # For function endpoints, return JSONResponse
            return JSONResponse(
                content=content,
                status_code=status_code,
                headers=headers,
                media_type=media_type,
            )

    async def success(
        self,
        data: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Generate a successful response (200 OK).

        Args:
            data: Response data
            message: Optional success message
            headers: Optional HTTP headers

        Returns:
            Success response
        """
        content: Dict[str, Any] = {}
        if data is not None:
            content["data"] = data
        if message is not None:
            content["message"] = message

        final_content = (
            content if content else {"data": data} if data is not None else content
        )
        return await self.response(
            content=final_content,
            status_code=200,
            headers=headers,
        )

    async def created(
        self,
        data: Any = None,
        message: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create a resource created response (201 Created).

        Args:
            data: Created resource data
            message: Optional creation message
            headers: Optional HTTP headers

        Returns:
            Created response
        """
        content: Dict[str, Any] = {}
        if data is not None:
            content["data"] = data
        if message is not None:
            content["message"] = message

        final_content = (
            content if content else {"data": data} if data is not None else content
        )
        return await self.response(
            content=final_content,
            status_code=201,
            headers=headers,
        )

    async def no_content(
        self, headers: Optional[Dict[str, str]] = None
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create a no content response (204 No Content).

        Args:
            headers: Optional HTTP headers

        Returns:
            No content response
        """
        return await self.response(
            content=None,
            status_code=204,
            headers=headers,
        )

    async def error(
        self,
        message: str,
        status_code: int = 400,
        details: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create an error response.

        Args:
            message: Error message
            status_code: HTTP status code
            details: Optional error details
            headers: Optional HTTP headers

        Returns:
            Error response
        """
        content: Dict[str, Any] = {"error": message}
        if details is not None:
            content["details"] = details

        return await self.response(
            content=content,
            status_code=status_code,
            headers=headers,
        )

    async def bad_request(
        self,
        message: str = "Bad Request",
        details: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create a bad request response (400 Bad Request).

        Args:
            message: Error message
            details: Optional error details
            headers: Optional HTTP headers

        Returns:
            Bad request response
        """
        return await self.error(
            message=message,
            status_code=400,
            details=details,
            headers=headers,
        )

    async def unauthorized(
        self,
        message: str = "Unauthorized",
        details: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create an unauthorized response (401 Unauthorized).

        Args:
            message: Error message
            details: Optional error details
            headers: Optional HTTP headers

        Returns:
            Unauthorized response
        """
        return await self.error(
            message=message,
            status_code=401,
            details=details,
            headers=headers,
        )

    async def forbidden(
        self,
        message: str = "Forbidden",
        details: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create a forbidden response (403 Forbidden).

        Args:
            message: Error message
            details: Optional error details
            headers: Optional HTTP headers

        Returns:
            Forbidden response
        """
        return await self.error(
            message=message,
            status_code=403,
            details=details,
            headers=headers,
        )

    async def not_found(
        self,
        message: str = "Not Found",
        details: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create a not found response (404 Not Found).

        Args:
            message: Error message
            details: Optional error details
            headers: Optional HTTP headers

        Returns:
            Not found response
        """
        return await self.error(
            message=message,
            status_code=404,
            details=details,
            headers=headers,
        )

    async def conflict(
        self,
        message: str = "Conflict",
        details: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create a conflict response (409 Conflict).

        Args:
            message: Error message
            details: Optional error details
            headers: Optional HTTP headers

        Returns:
            Conflict response
        """
        return await self.error(
            message=message,
            status_code=409,
            details=details,
            headers=headers,
        )

    async def unprocessable_entity(
        self,
        message: str = "Unprocessable Entity",
        details: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create an unprocessable entity response (422 Unprocessable Entity).

        Args:
            message: Error message
            details: Optional error details
            headers: Optional HTTP headers

        Returns:
            Unprocessable entity response
        """
        return await self.error(
            message=message,
            status_code=422,
            details=details,
            headers=headers,
        )

    async def internal_server_error(
        self,
        message: str = "Internal Server Error",
        details: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create an internal server error response (500 Internal Server Error).

        Args:
            message: Error message
            details: Optional error details
            headers: Optional HTTP headers

        Returns:
            Internal server error response
        """
        return await self.error(
            message=message,
            status_code=500,
            details=details,
            headers=headers,
        )

    def exception(
        self,
        status_code: int,
        *,
        detail: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """Raise an HTTP exception.

        Args:
            status_code: HTTP status code
            detail: Error detail
            headers: Optional response headers

        Raises:
            HTTPException: Always
        """
        raise HTTPException(
            status_code=status_code,
            detail=detail,
            headers=headers,
        )


# ============================================================================
# Factory Function
# ============================================================================


def create_endpoint_helper(
    walker_instance: Optional[Any] = None,
) -> ResponseHelper:
    """Factory function to create an endpoint response helper.

    Args:
        walker_instance: Optional walker instance for response property updates

    Returns:
        Configured ResponseHelper instance

    Example:
        >>> helper = create_endpoint_helper()
        >>> helper.success(data={"user": "john"})
    """
    return ResponseHelper(walker_instance=walker_instance)


__all__ = [
    # Type definitions
    "APIResponse",
    "SuccessResponse",
    "ErrorResponse",
    # Formatting utilities
    "format_response",
    # Response classes
    "EndpointResponse",
    "ResponseHelper",
    # Factory function
    "create_endpoint_helper",
]
