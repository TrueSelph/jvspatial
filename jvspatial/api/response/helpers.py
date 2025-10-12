"""Response helper utilities for jvspatial API."""

from typing import Any, Dict, Optional, Union

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from jvspatial.core.entities import Walker


class ResponseHelper:
    """Helper class for generating API responses."""

    def __init__(self, *, walker_instance: Optional[Walker] = None) -> None:
        """Initialize the response helper.

        Args:
            walker_instance: Optional walker instance to update response property
        """
        self.walker_instance = walker_instance

    def response(
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
                self.walker_instance.report(response_dict)
            return response_dict
        else:
            # For function endpoints, return JSONResponse
            return JSONResponse(
                content=content,
                status_code=status_code,
                headers=headers,
                media_type=media_type,
            )

    def success(
        self,
        data: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Generate a successful response.

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
        return self.response(
            content=final_content,
            status_code=200,
            headers=headers,
        )

    def created(
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
        return self.response(
            content=final_content,
            status_code=201,
            headers=headers,
        )

    def no_content(
        self, headers: Optional[Dict[str, str]] = None
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create a no content response (204 No Content).

        Args:
            headers: Optional HTTP headers

        Returns:
            No content response
        """
        return self.response(
            content=None,
            status_code=204,
            headers=headers,
        )

    def error(
        self,
        message: str,
        status_code: int = 400,
        details: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create an error response.

        Args:
            error: Error message
            status_code: HTTP status code
            details: Optional error details
            headers: Optional HTTP headers

        Returns:
            Error response
        """
        content: Dict[str, Any] = {"error": message}
        if details is not None:
            content["details"] = details

        return self.response(
            content=content,
            status_code=status_code,
            headers=headers,
        )

    def bad_request(
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
        return self.error(
            message=message,
            status_code=400,
            details=details,
            headers=headers,
        )

    def unauthorized(
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
        return self.error(
            message=message,
            status_code=401,
            details=details,
            headers=headers,
        )

    def forbidden(
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
        return self.error(
            message=message,
            status_code=403,
            details=details,
            headers=headers,
        )

    def not_found(
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
        return self.error(
            message=message,
            status_code=404,
            details=details,
            headers=headers,
        )

    def conflict(
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
        return self.error(
            message=message,
            status_code=409,
            details=details,
            headers=headers,
        )

    def unprocessable_entity(
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
        return self.error(
            message=message,
            status_code=422,
            details=details,
            headers=headers,
        )

    def internal_server_error(
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
        return self.error(
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


def create_endpoint_helper(
    walker_instance: Optional[Any] = None,
) -> ResponseHelper:
    """Factory function to create an endpoint response helper.

    Args:
        walker_instance: Optional walker instance for response property updates

    Returns:
        Configured ResponseHelper instance
    """
    return ResponseHelper(walker_instance=walker_instance)
