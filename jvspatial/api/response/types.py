"""Response type definitions for jvspatial API."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


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
