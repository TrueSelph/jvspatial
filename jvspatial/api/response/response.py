"""Response class implementation."""

from typing import Any, Dict, Optional

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
