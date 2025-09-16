"""API module for defining FastAPI routes for walkers with enhanced Field-based parameter control."""

import ast
import inspect
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, Union

from fastapi import APIRouter, Body, HTTPException
from pydantic import (
    BaseModel,
    ConfigDict,
)
from pydantic import Field as PydanticField
from pydantic import (
    ValidationError,
    create_model,
)
from pydantic.fields import FieldInfo, PydanticUndefined

from jvspatial.core.entities import Node, Walker

# Module-level Body instance to avoid B008 flake8 warning
DEFAULT_BODY = Body()


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


class ParameterModelFactory:
    """Factory for creating Pydantic models from Walker classes using Field metadata.

    This class supports both the new EndpointField-based approach and the legacy
    comment-based approach for backward compatibility.
    """

    @classmethod
    def create_model(
        cls: Type["ParameterModelFactory"], walker_cls: Type[Walker]
    ) -> Type[BaseModel]:
        """Create parameter model using Field metadata with fallback to AST parsing.

        Args:
            walker_cls: Walker class to create parameter model for

        Returns:
            Pydantic model class for endpoint parameters
        """
        # Check if walker uses the new EndpointField approach
        uses_endpoint_fields = cls._uses_endpoint_fields(walker_cls)

        if uses_endpoint_fields:
            return cls._create_model_from_fields(walker_cls)
        else:
            return cls._create_model_legacy(walker_cls)

    @classmethod
    def _uses_endpoint_fields(
        cls: Type["ParameterModelFactory"], walker_cls: Type[Walker]
    ) -> bool:
        """Check if walker class uses EndpointField-based configuration.

        Args:
            walker_cls: Walker class to check

        Returns:
            True if any field has endpoint configuration
        """
        for _name, field_info in walker_cls.model_fields.items():
            endpoint_config = cls._extract_endpoint_config(field_info)
            if endpoint_config:  # If any field has endpoint config, use new system
                return True
        return False

    @classmethod
    def _create_model_legacy(
        cls: Type["ParameterModelFactory"], walker_cls: Type[Walker]
    ) -> Type[BaseModel]:
        """Legacy model creation using AST parsing and without endpoint field metadata.

        Args:
            walker_cls: Walker class to create parameter model for

        Returns:
            Pydantic model class for endpoint parameters
        """
        # Get fields to ignore from comment-based configuration
        ignored_fields = cls._get_ignored_fields(walker_cls)

        # Prepare fields dictionary for model creation
        fields = {}

        # Walker base fields that should be excluded by default
        walker_base_fields = {"id", "queue", "response", "current_node", "paused"}

        for name, field in walker_cls.model_fields.items():
            if name in ignored_fields:
                continue
            # Skip Walker base fields unless they have comment-based endpoint configuration
            if name in walker_base_fields and name not in ignored_fields:
                continue
            annotation = field.annotation
            default = field.default if field.default is not None else ...
            fields[name] = (annotation, default)

        fields["start_node"] = (Optional[str], None)

        return create_model(
            f"{walker_cls.__name__}ParameterModel",
            __config__=ConfigDict(extra="forbid"),
            **fields,
        )

    @classmethod
    def _create_model_from_fields(
        cls: Type["ParameterModelFactory"], walker_cls: Type[Walker]
    ) -> Type[BaseModel]:
        """Create parameter model using Field metadata approach.

        Args:
            walker_cls: Walker class to process

        Returns:
            Parameter model with Field-based configuration
        """
        fields = {}
        grouped_fields = defaultdict(list)

        # Walker base fields that should be excluded unless explicitly configured
        walker_base_fields = {"id", "queue", "response", "current_node", "paused"}

        for name, field_info in walker_cls.model_fields.items():
            endpoint_config = cls._extract_endpoint_config(field_info)

            # Skip Walker base fields unless they have endpoint configuration
            if name in walker_base_fields and not endpoint_config:
                continue

            # Skip excluded fields
            if endpoint_config.get("exclude_endpoint", False):
                continue

            # Build parameter field
            param_name = endpoint_config.get("endpoint_name") or name
            field_tuple = cls._build_parameter_field(name, field_info, endpoint_config)

            # Handle field grouping
            group = endpoint_config.get("endpoint_group")
            if group:
                grouped_fields[group].append((param_name, field_tuple))
            else:
                fields[param_name] = field_tuple

        # Add grouped fields as nested models if groups exist
        for group_name, group_fields in grouped_fields.items():
            if group_fields:
                group_model = cls._create_group_model(group_name, group_fields)
                fields[group_name] = (
                    Optional[group_model],  # type: ignore[assignment]
                    PydanticField(default=None),
                )

        # Always include start_node parameter
        fields["start_node"] = (
            Optional[str],  # type: ignore[assignment]
            PydanticField(
                default=None,
                description="Starting node ID for graph traversal",
                examples=["n:Node:123", "n:Root:root"],
            ),
        )

        # Create the parameter model with strict validation
        model_name = f"{walker_cls.__name__}ParameterModel"
        return create_model(model_name, __config__=ConfigDict(extra="forbid"), **fields)

    @classmethod
    def _extract_endpoint_config(
        cls: Type["ParameterModelFactory"], field_info: FieldInfo
    ) -> Dict[str, Any]:
        """Extract endpoint configuration from Field metadata.

        Args:
            field_info: Pydantic FieldInfo object

        Returns:
            Dictionary of endpoint configuration options
        """
        json_schema_extra = getattr(field_info, "json_schema_extra", None)

        if callable(json_schema_extra):
            # Handle callable json_schema_extra
            try:
                schema: Dict[str, Any] = {}
                json_schema_extra(schema, type(None))
                return schema.get("endpoint_config", {})
            except Exception:
                return {}
        elif isinstance(json_schema_extra, dict):
            return json_schema_extra.get("endpoint_config", {})

        return {}

    @classmethod
    def _build_parameter_field(
        cls: Type["ParameterModelFactory"],
        original_name: str,
        original_field: FieldInfo,
        endpoint_config: Dict[str, Any],
    ) -> Tuple[Type, FieldInfo]:
        """Build parameter field with endpoint-specific configuration.

        Args:
            original_name: Original field name
            original_field: Original FieldInfo
            endpoint_config: Endpoint configuration dictionary

        Returns:
            Tuple of (field_type, FieldInfo) for parameter model
        """
        # Get original field properties
        field_type = original_field.annotation
        default_value = original_field.default

        # Handle endpoint-specific required override
        if endpoint_config.get("endpoint_required") is not None:
            if endpoint_config["endpoint_required"]:
                # Make field required for endpoint
                if default_value is None:
                    default_value = PydanticUndefined
                # Don't change type if it's already required
            else:
                # Make field optional for endpoint
                if not cls._is_optional_type(field_type):
                    field_type = Optional[field_type]
                if default_value is PydanticUndefined:
                    default_value = None

        # Build field configuration
        field_kwargs = {
            "title": original_field.title,
            "description": original_field.description,
        }

        # Add examples if available
        if hasattr(original_field, "examples") and original_field.examples:
            field_kwargs["examples"] = original_field.examples

        # Preserve original metadata (contains validation constraints)
        if hasattr(original_field, "metadata") and original_field.metadata:
            # Extract constraint values from metadata for field reconstruction
            for constraint in original_field.metadata:
                if hasattr(constraint, "gt"):
                    field_kwargs["gt"] = constraint.gt
                elif hasattr(constraint, "ge"):
                    field_kwargs["ge"] = constraint.ge
                elif hasattr(constraint, "lt"):
                    field_kwargs["lt"] = constraint.lt
                elif hasattr(constraint, "le"):
                    field_kwargs["le"] = constraint.le
                elif hasattr(constraint, "min_length"):
                    field_kwargs["min_length"] = constraint.min_length
                elif hasattr(constraint, "max_length"):
                    field_kwargs["max_length"] = constraint.max_length
                elif hasattr(constraint, "pattern"):
                    field_kwargs["pattern"] = constraint.pattern

        # Apply endpoint-specific constraints
        endpoint_constraints = endpoint_config.get("endpoint_constraints", {})
        field_kwargs.update(endpoint_constraints)

        # Handle OpenAPI-specific configuration
        def schema_extra(schema: Dict[str, Any], model_type: type) -> None:
            if endpoint_config.get("endpoint_deprecated"):
                schema["deprecated"] = True

            if endpoint_config.get("endpoint_hidden"):
                schema["writeOnly"] = True

            # Add any additional endpoint constraints to schema
            for key, value in endpoint_constraints.items():
                if key not in schema:
                    schema[key] = value

        # Set json_schema_extra if we have endpoint-specific config
        if (
            endpoint_config.get("endpoint_deprecated")
            or endpoint_config.get("endpoint_hidden")
            or endpoint_constraints
        ):
            field_kwargs["json_schema_extra"] = schema_extra

        # Remove None values
        field_kwargs = {k: v for k, v in field_kwargs.items() if v is not None}

        return (field_type, PydanticField(default_value, **field_kwargs))

    @classmethod
    def _is_optional_type(cls: Type["ParameterModelFactory"], field_type: Type) -> bool:
        """Check if a type is Optional (Union with None).

        Args:
            field_type: Type to check

        Returns:
            True if type is Optional
        """
        return (
            hasattr(field_type, "__origin__")
            and field_type.__origin__ is Union
            and type(None) in field_type.__args__
        )

    @classmethod
    def _create_group_model(
        cls: Type["ParameterModelFactory"],
        group_name: str,
        group_fields: List[Tuple[str, Tuple[Type, FieldInfo]]],
    ) -> Type[BaseModel]:
        """Create a nested model for grouped fields.

        Args:
            group_name: Name of the group
            group_fields: List of (field_name, field_tuple) pairs

        Returns:
            Pydantic model class for the group
        """
        fields: Dict[str, Any] = dict(group_fields)
        model_name = f"{group_name.title()}Group"
        return create_model(model_name, __config__=ConfigDict(extra="forbid"), **fields)

    @classmethod
    def _get_ignored_fields(
        cls: Type["ParameterModelFactory"], walker_cls: Type[Walker]
    ) -> Set[str]:
        """Legacy AST parsing for comment-based field exclusion.

        Args:
            walker_cls: Walker class to analyze

        Returns:
            Set of field names marked with '# endpoint: ignore'
        """
        try:
            source = inspect.getsource(walker_cls)
        except (TypeError, OSError):
            # Handle cases where source code is not available (e.g., dynamically created classes in tests)
            return set()

        # Remove leading indentation to make it parseable
        import textwrap

        source = textwrap.dedent(source)
        lines = source.split("\n")  # Split source into lines for analysis

        tree = ast.parse(source)
        ignored_fields = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for body_node in node.body:
                    if isinstance(body_node, (ast.AnnAssign, ast.Assign)):
                        field_names = []
                        if isinstance(body_node, ast.AnnAssign):
                            if isinstance(body_node.target, ast.Name):
                                field_names = [body_node.target.id]
                        elif isinstance(body_node, ast.Assign):
                            field_names = [
                                t.id
                                for t in body_node.targets
                                if isinstance(t, ast.Name)
                            ]

                        # Only check for same-line comments
                        current_line = lines[body_node.lineno - 1]
                        if "# endpoint: ignore" in current_line:
                            ignored_fields.update(field_names)
        return ignored_fields


class EndpointRouter:
    """Enhanced API router for graph-based walkers with Field-based parameter model generation.

    Usage:
        @router.endpoint("/path")
        class MyWalker(Walker):
            visible_field: str = EndpointField(description="Visible in API")
            hidden_field: str = EndpointField(exclude_endpoint=True)
    """

    def __init__(self: "EndpointRouter") -> None:
        """Initialize the EndpointRouter with an APIRouter."""
        self.router = APIRouter()

    def endpoint(
        self: "EndpointRouter",
        path: str,
        methods: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Callable[[Type[Walker]], Type[Walker]]:
        """Register a walker as an API endpoint with enhanced parameter model.

        Args:
            path: The URL path for the endpoint
            methods: HTTP methods allowed (default: ["POST"])
            **kwargs: Additional arguments for route configuration

        Returns:
            Decorator function for Walker classes
        """
        if methods is None:
            methods = ["POST"]

        def decorator(cls: Type[Walker]) -> Type[Walker]:
            # Use enhanced parameter model factory
            param_model = ParameterModelFactory.create_model(cls)

            # Use typing.Any for the parameter type to avoid mypy issues
            # FastAPI will use the param_model for request body validation
            async def handler(params: Any = DEFAULT_BODY) -> Dict[str, Any]:  # type: ignore[misc]
                # Extract start_node - handle both dict and Pydantic model
                start_node = None
                if isinstance(params, dict):
                    start_node = params.get("start_node")
                elif hasattr(params, "start_node"):
                    start_node = params.start_node

                # Handle grouped parameters
                walker_data = {}

                # Handle both dict (for direct testing) and Pydantic model parameters
                if isinstance(params, dict):
                    params_dict = params
                elif hasattr(params, "model_dump"):
                    params_dict = params.model_dump()
                else:
                    # Fallback for other object types
                    params_dict = {
                        k: getattr(params, k)
                        for k in dir(params)
                        if not k.startswith("_")
                    }

                for field_name, field_value in params_dict.items():
                    if field_name == "start_node":
                        continue

                    if isinstance(field_value, dict):
                        # Handle grouped fields passed as dictionaries
                        walker_data.update(field_value)
                    elif isinstance(field_value, BaseModel):
                        # Handle grouped fields passed as Pydantic models
                        walker_data.update(field_value.model_dump())
                    else:
                        walker_data[field_name] = field_value

                # Collect excluded field names
                excluded_fields = set()
                for field_name, field_info in cls.model_fields.items():
                    endpoint_config = ParameterModelFactory._extract_endpoint_config(
                        field_info
                    )
                    if endpoint_config.get("exclude_endpoint", False):
                        excluded_fields.add(field_name)

                # Check for excluded fields in request
                for field_name in excluded_fields:
                    if field_name in walker_data:
                        raise HTTPException(
                            status_code=422,
                            detail=f"Field '{field_name}' is excluded from endpoint and should not be provided",
                        )

                # Remove None values unless explicitly set
                walker_data = {k: v for k, v in walker_data.items() if v is not None}

                # Provide defaults for excluded fields that weren't in the request
                for field_name in excluded_fields:
                    if field_name not in walker_data:
                        field_info = cls.model_fields[field_name]
                        if field_info.default is not PydanticUndefined:
                            walker_data[field_name] = field_info.default
                        elif (
                            hasattr(field_info, "default_factory")
                            and field_info.default_factory
                        ):
                            walker_data[field_name] = field_info.default_factory()

                try:
                    walker = cls(**walker_data)
                except ValidationError as e:
                    raise HTTPException(status_code=422, detail=e.errors())

                # Execute walker with proper start node resolution
                start_node_obj = None
                if start_node:
                    # Try to retrieve the node by ID
                    start_node_obj = await Node.get(start_node)
                    if not start_node_obj:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Start node with ID '{start_node}' not found",
                        )
                result = await walker.spawn(start=start_node_obj)

                if result.response:
                    if (
                        "status" in result.response
                        and isinstance(result.response["status"], int)
                        and result.response["status"] >= 400
                    ):
                        raise HTTPException(
                            status_code=result.response["status"],
                            detail=result.response.get("detail", "Unknown error"),
                        )
                    return result.response
                return {}

            # Dynamically update the handler's signature to use the parameter model
            # Update handler annotation to use the actual param_model
            handler.__annotations__["params"] = param_model

            self.router.add_api_route(
                path, handler, methods=methods, response_model=dict, **kwargs
            )
            return cls

        return decorator
