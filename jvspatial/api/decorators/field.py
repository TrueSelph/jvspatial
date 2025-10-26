"""Field-level decorators for Pydantic models.

This module provides decorators that configure field behavior in API endpoints,
including OpenAPI documentation, validation, and field visibility. These
decorators are applied to Pydantic model fields.

Examples:
    class UserModel(BaseModel):
        name: str = endpoint_field(
            description="User name",
            endpoint_required=True
        )
        password: str = endpoint_field(
            exclude_endpoint=True  # Hide from API
        )
"""

from typing import Any, Dict, List, Optional

from pydantic import Field as PydanticField


class EndpointFieldInfo:
    """Container for endpoint-specific field configuration."""

    def __init__(
        self: "EndpointFieldInfo",
        exclude_endpoint: bool = False,
        endpoint_name: Optional[str] = None,
        endpoint_required: Optional[bool] = None,
        endpoint_hidden: bool = False,
        endpoint_deprecated: bool = False,
        endpoint_group: Optional[str] = None,
        endpoint_constraints: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize EndpointFieldInfo."""
        self.exclude_endpoint = exclude_endpoint
        self.endpoint_name = endpoint_name
        self.endpoint_required = endpoint_required
        self.endpoint_hidden = endpoint_hidden
        self.endpoint_deprecated = endpoint_deprecated
        self.endpoint_group = endpoint_group
        self.endpoint_constraints = endpoint_constraints or {}


def endpoint_field(
    default: Any = ...,
    *,
    # Standard Pydantic parameters
    title: Optional[str] = None,
    description: Optional[str] = None,
    examples: Optional[List[Any]] = None,
    gt: Optional[float] = None,
    ge: Optional[float] = None,
    lt: Optional[float] = None,
    le: Optional[float] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    pattern: Optional[str] = None,
    # Endpoint-specific parameters
    exclude_endpoint: bool = False,
    endpoint_name: Optional[str] = None,
    endpoint_required: Optional[bool] = None,
    endpoint_hidden: bool = False,
    endpoint_deprecated: bool = False,
    endpoint_group: Optional[str] = None,
    endpoint_constraints: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Any:
    """Enhanced Field function with endpoint configuration support.

    Args:
        default: Default value for the field
        title: OpenAPI title
        description: OpenAPI description
        examples: OpenAPI examples
        gt, ge, lt, le: Numeric validation constraints
        min_length, max_length: String length constraints
        regex: String pattern validation
        exclude_endpoint: Exclude field from endpoint entirely
        endpoint_name: Custom parameter name in API
        endpoint_required: Override required status for endpoint
        endpoint_hidden: Hide from OpenAPI documentation
        endpoint_deprecated: Mark as deprecated in OpenAPI
        endpoint_group: Group related parameters
        endpoint_constraints: Additional OpenAPI constraints
        **kwargs: Additional Pydantic Field parameters

    Returns:
        Pydantic Field with endpoint configuration
    """
    # Create endpoint configuration
    endpoint_config = EndpointFieldInfo(
        exclude_endpoint=exclude_endpoint,
        endpoint_name=endpoint_name,
        endpoint_required=endpoint_required,
        endpoint_hidden=endpoint_hidden,
        endpoint_deprecated=endpoint_deprecated,
        endpoint_group=endpoint_group,
        endpoint_constraints=endpoint_constraints,
    )

    # Store endpoint config in json_schema_extra
    def schema_extra(schema: Dict[str, Any], model_type: type) -> None:
        schema["endpoint_config"] = endpoint_config.__dict__

        # Apply endpoint-specific schema modifications
        if endpoint_deprecated:
            schema["deprecated"] = True

        if endpoint_hidden:
            schema["writeOnly"] = True  # Hide from generated docs

    # Handle existing json_schema_extra
    existing_extra = kwargs.get("json_schema_extra")
    if existing_extra:
        if callable(existing_extra):

            def combined_extra(schema: Dict[str, Any], model_type: type) -> None:
                existing_extra(schema, model_type)
                schema_extra(schema, model_type)

            kwargs["json_schema_extra"] = combined_extra
        else:
            kwargs["json_schema_extra"] = {**existing_extra, **endpoint_config.__dict__}
    else:
        kwargs["json_schema_extra"] = schema_extra

    return PydanticField(
        default=default,
        title=title,
        description=description,
        examples=examples,
        gt=gt,
        ge=ge,
        lt=lt,
        le=le,
        min_length=min_length,
        max_length=max_length,
        pattern=pattern,
        **kwargs,
    )


# Backward compatibility alias
EndpointField = endpoint_field
