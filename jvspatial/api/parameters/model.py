"""Parameter model definitions for endpoints."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EndpointParameterModel(BaseModel):
    """Base model for endpoint parameters."""

    model_config = ConfigDict(extra="forbid")

    # Always include start_node parameter
    start_node: Optional[str] = Field(
        default=None,
        description="Starting node ID for graph traversal",
        examples=["n:Root:root"],
    )
