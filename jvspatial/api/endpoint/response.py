"""Response utilities for jvspatial endpoints with flexible response handling."""

from typing import Any, Dict, Optional, Union

from fastapi.responses import JSONResponse


class EndpointResponse:
    """Flexible response handler for jvspatial endpoints.

    This class provides a unified interface for creating HTTP responses
    with configurable status codes, content, headers, and media types.
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

    def to_json_response(self) -> JSONResponse:
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

    def to_dict(self) -> Dict[str, Any]:
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


class EndpointResponseHelper:
    """Helper class that provides convenient response methods for endpoints.

    This class is injected into walkers and endpoint functions to provide
    a clean, semantic API for creating responses.
    """

    def __init__(self, walker_instance: Optional[Any] = None) -> None:
        """Initialize response helper.

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
        endpoint_response = EndpointResponse(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
        )

        if self.walker_instance is not None:
            # For walkers, set response property (backwards compatibility)
            # and also add to report if the walker has a report method
            response_dict = endpoint_response.to_dict()

            # Set response property for backwards compatibility with existing tests
            self.walker_instance.response = response_dict

            # Also add to report if available (for proper walkers)
            if hasattr(self.walker_instance, "report"):
                self.walker_instance.report(response_dict)

            return response_dict
        else:
            # For function endpoints, return JSONResponse directly
            return endpoint_response.to_json_response()

    def success(
        self,
        data: Any = None,
        message: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create a successful response (200 OK).

        Args:
            data: Success payload data
            message: Optional success message
            headers: Optional HTTP headers

        Returns:
            Success response
        """
        content = {}
        if data is not None:
            content["data"] = data
        if message is not None:
            content["message"] = message

        return self.response(
            content=content if content else data, status_code=200, headers=headers
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
        content = {}
        if data is not None:
            content["data"] = data
        if message is not None:
            content["message"] = message

        return self.response(
            content=content if content else data, status_code=201, headers=headers
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
        return self.response(content=None, status_code=204, headers=headers)

    def error(
        self,
        message: str,
        status_code: int = 400,
        details: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[JSONResponse, Dict[str, Any]]:
        """Create an error response.

        Args:
            message: Error message
            status_code: HTTP error status code
            details: Optional error details
            headers: Optional HTTP headers

        Returns:
            Error response
        """
        content = {"error": message}
        if details is not None:
            content["details"] = details

        return self.response(content=content, status_code=status_code, headers=headers)

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
            message=message, status_code=400, details=details, headers=headers
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
            message=message, status_code=401, details=details, headers=headers
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
            message=message, status_code=403, details=details, headers=headers
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
            message=message, status_code=404, details=details, headers=headers
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
            message=message, status_code=409, details=details, headers=headers
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
            message=message, status_code=422, details=details, headers=headers
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
            message=message, status_code=500, details=details, headers=headers
        )


def create_endpoint_helper(
    walker_instance: Optional[Any] = None,
) -> EndpointResponseHelper:
    """Factory function to create an endpoint response helper.

    Args:
        walker_instance: Optional walker instance for response property updates

    Returns:
        Configured EndpointResponseHelper instance
    """
    return EndpointResponseHelper(walker_instance=walker_instance)
