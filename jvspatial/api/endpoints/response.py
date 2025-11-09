"""Consolidated response handling for jvspatial API.

This module provides all response-related functionality including:
- Response type definitions (SuccessResponse, ErrorResponse)
- Response formatting utilities
- Response helper class with convenience methods
- Low-level response wrapper class
- Response schema definition system for @endpoint decorator
"""

from typing import Any, Dict, List, Optional, Type, Union

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
    message: Optional[str] = None,
    success: bool = True,
) -> Dict[str, Any]:
    """Format a response dictionary.

    Args:
        data: Response data
        message: Optional message
        success: Whether the response represents success

    Returns:
        Formatted response dictionary
    """
    response = {"success": success}
    if message is not None:
        response["message"] = message
    if data is not None:
        response["data"] = data
    return response


class EndpointResponse:
    """Response wrapper for endpoint handlers."""

    def __init__(
        self,
        content: Optional[Any] = None,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        media_type: str = "application/json",
    ):
        """Initialize endpoint response.

        Args:
            content: Response content (dict, string, or any serializable object)
            status_code: HTTP status code
            headers: Optional response headers
            media_type: Content type
        """
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.media_type = media_type

    async def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Response dictionary with status, message, data, headers fields
        """
        result = {"status": self.status_code}

        # Handle content based on type
        if self.content is None:
            # None content - just return status
            pass
        elif isinstance(self.content, dict):
            # If content is a dict, merge all its fields into result
            if self.content:  # Non-empty dict
                result.update(self.content)
            # Empty dict - just return status (already set)
        else:
            # Non-dict content goes into "data" field
            result["data"] = self.content

        # Add headers if present
        if self.headers:
            result["headers"] = self.headers

        return result

    async def to_json_response(self) -> JSONResponse:
        """Convert to FastAPI JSONResponse.

        Returns:
            JSONResponse instance
        """
        content_dict = await self.to_dict()
        # Extract the actual content (status should not be in JSONResponse content)
        json_content = {k: v for k, v in content_dict.items() if k != "status"}
        return JSONResponse(
            content=json_content,
            status_code=self.status_code,
            headers=self.headers,
            media_type=self.media_type,
        )


class ResponseHelper:
    """Helper class for Walker responses."""

    def __init__(self, walker_instance: Optional[Walker] = None):
        """Initialize response helper.

        Args:
            walker_instance: Optional Walker instance
        """
        self.walker_instance = walker_instance

    async def response(
        self,
        content: Optional[Dict[str, Any]] = None,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[Dict[str, Any], JSONResponse]:
        """Create a custom response.

        Args:
            content: Response content
            status_code: HTTP status code
            headers: Optional headers

        Returns:
            Dict for walkers, JSONResponse for function endpoints
        """
        response_data = {"status": status_code}
        if content:
            response_data.update(content)
        if headers:
            response_data["headers"] = headers or {}

        if self.walker_instance:
            # Store response on walker instance and add to report
            if not hasattr(self.walker_instance, "response"):
                self.walker_instance.response = None
            self.walker_instance.response = response_data
            # Add to walker's report so it can be retrieved via get_report()
            if hasattr(self.walker_instance, "report"):
                await self.walker_instance.report(response_data)
            return response_data
        else:
            # Return JSONResponse for function endpoints
            return JSONResponse(
                content=content or {},
                status_code=status_code,
                headers=headers,
            )

    async def success(
        self,
        data: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> Union[Dict[str, Any], JSONResponse]:
        """Create success response.

        Args:
            data: Response data
            message: Optional message

        Returns:
            Dict for walkers, JSONResponse for function endpoints
        """
        response_data = {"status": 200}
        if message:
            response_data["message"] = message
        if data:
            response_data["data"] = data

        if self.walker_instance:
            if not hasattr(self.walker_instance, "response"):
                self.walker_instance.response = None
            self.walker_instance.response = response_data
            # Add to walker's report so it can be retrieved via get_report()
            if hasattr(self.walker_instance, "report"):
                await self.walker_instance.report(response_data)
            return response_data
        else:
            content = {}
            if message:
                content["message"] = message
            if data:
                content["data"] = data
            return JSONResponse(content=content, status_code=200)

    async def created(
        self,
        data: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[Dict[str, Any], JSONResponse]:
        """Create 201 Created response.

        Args:
            data: Response data
            message: Optional message
            headers: Optional headers

        Returns:
            Dict for walkers, JSONResponse for function endpoints
        """
        response_data = {"status": 201}
        if message:
            response_data["message"] = message
        if data:
            response_data["data"] = data
        if headers:
            response_data["headers"] = headers

        if self.walker_instance:
            if not hasattr(self.walker_instance, "response"):
                self.walker_instance.response = None
            self.walker_instance.response = response_data
            # Add to walker's report so it can be retrieved via get_report()
            if hasattr(self.walker_instance, "report"):
                await self.walker_instance.report(response_data)
            return response_data
        else:
            content = {}
            if message:
                content["message"] = message
            if data:
                content["data"] = data
            return JSONResponse(content=content, status_code=201, headers=headers)

    async def no_content(
        self,
        headers: Optional[Dict[str, str]] = None,
    ) -> Union[Dict[str, Any], JSONResponse]:
        """Create 204 No Content response.

        Args:
            headers: Optional headers

        Returns:
            Dict for walkers, JSONResponse for function endpoints
        """
        response_data = {"status": 204}
        if headers:
            response_data["headers"] = headers

        if self.walker_instance:
            if not hasattr(self.walker_instance, "response"):
                self.walker_instance.response = None
            self.walker_instance.response = response_data
            # Add to walker's report so it can be retrieved via get_report()
            if hasattr(self.walker_instance, "report"):
                await self.walker_instance.report(response_data)
            return response_data
        else:
            return JSONResponse(content=None, status_code=204, headers=headers)

    async def bad_request(
        self,
        message: str = "Bad Request",
        details: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], JSONResponse]:
        """Create 400 Bad Request response.

        Args:
            message: Error message
            details: Optional error details

        Returns:
            Dict for walkers, JSONResponse for function endpoints
        """
        response_data = {"status": 400, "error": message}
        if details:
            response_data["details"] = details

        if self.walker_instance:
            if not hasattr(self.walker_instance, "response"):
                self.walker_instance.response = None
            self.walker_instance.response = response_data
            # Add to walker's report so it can be retrieved via get_report()
            if hasattr(self.walker_instance, "report"):
                await self.walker_instance.report(response_data)
            return response_data
        else:
            content = {"error": message}
            if details:
                content["details"] = details
            return JSONResponse(content=content, status_code=400)

    async def unauthorized(
        self,
        message: str = "Unauthorized",
        details: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], JSONResponse]:
        """Create 401 Unauthorized response.

        Args:
            message: Error message
            details: Optional error details

        Returns:
            Dict for walkers, JSONResponse for function endpoints
        """
        response_data = {"status": 401, "error": message}
        if details:
            response_data["details"] = details

        if self.walker_instance:
            if not hasattr(self.walker_instance, "response"):
                self.walker_instance.response = None
            self.walker_instance.response = response_data
            # Add to walker's report so it can be retrieved via get_report()
            if hasattr(self.walker_instance, "report"):
                await self.walker_instance.report(response_data)
            return response_data
        else:
            content = {"error": message}
            if details:
                content["details"] = details
            return JSONResponse(content=content, status_code=401)

    async def forbidden(
        self,
        message: str = "Forbidden",
        details: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], JSONResponse]:
        """Create 403 Forbidden response.

        Args:
            message: Error message
            details: Optional error details

        Returns:
            Dict for walkers, JSONResponse for function endpoints
        """
        response_data = {"status": 403, "error": message}
        if details:
            response_data["details"] = details

        if self.walker_instance:
            if not hasattr(self.walker_instance, "response"):
                self.walker_instance.response = None
            self.walker_instance.response = response_data
            # Add to walker's report so it can be retrieved via get_report()
            if hasattr(self.walker_instance, "report"):
                await self.walker_instance.report(response_data)
            return response_data
        else:
            content = {"error": message}
            if details:
                content["details"] = details
            return JSONResponse(content=content, status_code=403)

    async def not_found(
        self,
        message: str = "Not Found",
        details: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], JSONResponse]:
        """Create 404 Not Found response.

        Args:
            message: Error message
            details: Optional error details

        Returns:
            Dict for walkers, JSONResponse for function endpoints
        """
        response_data = {"status": 404, "error": message}
        if details:
            response_data["details"] = details

        if self.walker_instance:
            if not hasattr(self.walker_instance, "response"):
                self.walker_instance.response = None
            self.walker_instance.response = response_data
            # Add to walker's report so it can be retrieved via get_report()
            if hasattr(self.walker_instance, "report"):
                await self.walker_instance.report(response_data)
            return response_data
        else:
            content = {"error": message}
            if details:
                content["details"] = details
            return JSONResponse(content=content, status_code=404)

    async def conflict(
        self,
        message: str = "Conflict",
        details: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], JSONResponse]:
        """Create 409 Conflict response.

        Args:
            message: Error message
            details: Optional error details

        Returns:
            Dict for walkers, JSONResponse for function endpoints
        """
        response_data = {"status": 409, "error": message}
        if details:
            response_data["details"] = details

        if self.walker_instance:
            if not hasattr(self.walker_instance, "response"):
                self.walker_instance.response = None
            self.walker_instance.response = response_data
            # Add to walker's report so it can be retrieved via get_report()
            if hasattr(self.walker_instance, "report"):
                await self.walker_instance.report(response_data)
            return response_data
        else:
            content = {"error": message}
            if details:
                content["details"] = details
            return JSONResponse(content=content, status_code=409)

    async def unprocessable_entity(
        self,
        message: str = "Unprocessable Entity",
        details: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], JSONResponse]:
        """Create 422 Unprocessable Entity response.

        Args:
            message: Error message
            details: Optional error details

        Returns:
            Dict for walkers, JSONResponse for function endpoints
        """
        response_data = {"status": 422, "error": message}
        if details:
            response_data["details"] = details

        if self.walker_instance:
            if not hasattr(self.walker_instance, "response"):
                self.walker_instance.response = None
            self.walker_instance.response = response_data
            # Add to walker's report so it can be retrieved via get_report()
            if hasattr(self.walker_instance, "report"):
                await self.walker_instance.report(response_data)
            return response_data
        else:
            content = {"error": message}
            if details:
                content["details"] = details
            return JSONResponse(content=content, status_code=422)

    async def internal_server_error(
        self,
        message: str = "Internal Server Error",
        details: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], JSONResponse]:
        """Create 500 Internal Server Error response.

        Args:
            message: Error message
            details: Optional error details

        Returns:
            Dict for walkers, JSONResponse for function endpoints
        """
        response_data = {"status": 500, "error": message}
        if details:
            response_data["details"] = details

        if self.walker_instance:
            if not hasattr(self.walker_instance, "response"):
                self.walker_instance.response = None
            self.walker_instance.response = response_data
            # Add to walker's report so it can be retrieved via get_report()
            if hasattr(self.walker_instance, "report"):
                await self.walker_instance.report(response_data)
            return response_data
        else:
            content = {"error": message}
            if details:
                content["details"] = details
            return JSONResponse(content=content, status_code=500)

    async def error(
        self,
        message: str,
        status_code: int = 400,
        details: Optional[Dict[str, Any]] = None,
    ) -> Union[Dict[str, Any], JSONResponse]:
        """Create error response with custom status code.

        Args:
            message: Error message
            status_code: HTTP status code
            details: Optional error details

        Returns:
            Dict for walkers, JSONResponse for function endpoints
        """
        response_data = {"status": status_code, "error": message}
        if details:
            response_data["details"] = details

        if self.walker_instance:
            if not hasattr(self.walker_instance, "response"):
                self.walker_instance.response = None
            self.walker_instance.response = response_data
            # Add to walker's report so it can be retrieved via get_report()
            if hasattr(self.walker_instance, "report"):
                await self.walker_instance.report(response_data)
            return response_data
        else:
            content = {"error": message}
            if details:
                content["details"] = details
            return JSONResponse(content=content, status_code=status_code)

    def raise_error(
        self,
        status_code: int,
        error: str,
        detail: Optional[str] = None,
        code: Optional[str] = None,
    ) -> None:
        """Raise HTTP exception.

        Args:
            status_code: HTTP status code
            error: Error message
            detail: Optional error detail
            code: Optional error code
        """
        raise HTTPException(
            status_code=status_code,
            detail={
                "error": error,
                "detail": detail,
                "code": code,
            },
        )


def create_endpoint_helper(walker_instance: Optional[Walker] = None) -> ResponseHelper:
    """Create response helper instance.

    Args:
        walker_instance: Optional Walker instance

    Returns:
        ResponseHelper instance
    """
    return ResponseHelper(walker_instance)


# ============================================================================
# Response Schema Definition System
# ============================================================================


class ResponseField:
    """Field definition for API response schemas.

    Similar to EndpointField but for response definitions.
    """

    def __init__(
        self,
        field_type: Type[Any],
        description: str = "",
        example: Any = None,
        examples: Optional[List[Any]] = None,
        **kwargs: Any,
    ):
        """Initialize response field.

        Args:
            field_type: The type of the field
            description: Description of the field
            example: Single example value
            examples: List of example values
            **kwargs: Additional Pydantic field arguments
        """
        self.field_type = field_type
        self.description = description
        self.example = example
        self.examples = examples or ([example] if example is not None else [])
        self.kwargs = kwargs


class ResponseSchema:
    """Response schema definition for endpoints.

    This class allows developers to define the expected response structure
    for their endpoints in a programmatic way.
    """

    def __init__(
        self,
        success: bool = True,
        message: Optional[str] = None,
        data: Optional[Dict[str, ResponseField]] = None,
        error: Optional[Dict[str, ResponseField]] = None,
        **kwargs: Any,
    ):
        """Initialize response schema.

        Args:
            success: Whether the response represents success
            message: Optional message field
            data: Data fields for successful responses
            error: Error fields for error responses
            **kwargs: Additional fields
        """
        self.success = success
        self.message = message
        self.data = data or {}
        self.error = error or {}
        self.kwargs = kwargs

    def to_pydantic_model(self, model_name: str) -> Type[BaseModel]:
        """Convert response schema to Pydantic model.

        Args:
            model_name: Name for the generated model

        Returns:
            Pydantic model class
        """
        # Create a proper namespace with annotations
        namespace = {
            "__annotations__": {},
            "model_config": ConfigDict(extra="forbid"),
        }
        example: Dict[str, Any] = {}

        # Add success field
        namespace["__annotations__"]["success"] = bool
        namespace["success"] = Field(
            default=self.success, description="Whether the request was successful"
        )
        example["success"] = self.success

        # Add message field if specified
        if self.message is not None:
            namespace["__annotations__"]["message"] = Optional[str]
            namespace["message"] = Field(default=None, description="Response message")
            # don't set example for message unless provided via kwargs

        # Add data fields for successful responses
        if self.success and self.data:
            for field_name, field_def in self.data.items():
                namespace["__annotations__"][field_name] = field_def.field_type
                field_config = {
                    "description": field_def.description,
                    "examples": field_def.examples,
                }
                field_config.update(field_def.kwargs)
                namespace[field_name] = Field(**field_config)
                # compose example if available
                if field_def.examples:
                    example[field_name] = field_def.examples[0]

        # Add error fields for error responses
        if not self.success and self.error:
            for field_name, field_def in self.error.items():
                namespace["__annotations__"][field_name] = field_def.field_type
                field_config = {
                    "description": field_def.description,
                    "examples": field_def.examples,
                }
                field_config.update(field_def.kwargs)
                namespace[field_name] = Field(**field_config)
                if field_def.examples:
                    example[field_name] = field_def.examples[0]

        # Add any additional fields
        for field_name, field_value in self.kwargs.items():
            if isinstance(field_value, ResponseField):
                namespace["__annotations__"][field_name] = field_value.field_type
                field_config = {
                    "description": field_value.description,
                    "examples": field_value.examples,
                }
                field_config.update(field_value.kwargs)
                namespace[field_name] = Field(**field_config)
                if field_value.examples:
                    example[field_name] = field_value.examples[0]
            else:
                field_type = type(field_value)
                namespace["__annotations__"][field_name] = field_type
                namespace[field_name] = Field(default=field_value)
                example[field_name] = field_value

        # Attach model-level example via model_config
        if example:
            # Merge into existing model_config
            current_cfg: ConfigDict = namespace.get("model_config", ConfigDict())
            merged_cfg = ConfigDict(
                **{**current_cfg, "json_schema_extra": {"example": example}}
            )
            namespace["model_config"] = merged_cfg

        # Create the model
        return type(model_name, (BaseModel,), namespace)


def response_schema(
    success: bool = True,
    message: Optional[str] = None,
    data: Optional[Dict[str, ResponseField]] = None,
    error: Optional[Dict[str, ResponseField]] = None,
    **kwargs: Any,
) -> ResponseSchema:
    """Create a response schema definition.

    Args:
        success: Whether the response represents success
        message: Optional message field
        data: Data fields for successful responses
        error: Error fields for error responses
        **kwargs: Additional fields

    Returns:
        ResponseSchema instance

    Example:
        @endpoint("/users", response=response_schema(
            data={
                "users": ResponseField(
                    field_type=List[Dict[str, Any]],
                    description="List of users",
                    example=[{"id": 1, "name": "John"}]
                ),
                "count": ResponseField(
                    field_type=int,
                    description="Total number of users",
                    example=1
                )
            }
        ))
        def get_users():
            return {"users": [], "count": 0}
    """
    return ResponseSchema(
        success=success, message=message, data=data, error=error, **kwargs
    )


# Convenience functions for common response patterns
def success_response(
    data: Optional[Dict[str, ResponseField]] = None,
    message: Optional[str] = None,
    **kwargs: Any,
) -> ResponseSchema:
    """Create a success response schema.

    Args:
        data: Data fields
        message: Optional message
        **kwargs: Additional fields

    Returns:
        ResponseSchema for success responses
    """
    return ResponseSchema(success=True, message=message, data=data, **kwargs)


def error_response(
    error: Optional[Dict[str, ResponseField]] = None,
    message: Optional[str] = None,
    **kwargs: Any,
) -> ResponseSchema:
    """Create an error response schema.

    Args:
        error: Error fields
        message: Optional message
        **kwargs: Additional fields

    Returns:
        ResponseSchema for error responses
    """
    return ResponseSchema(success=False, message=message, error=error, **kwargs)
