"""Factory for creating parameter models from Walker classes."""

import inspect
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union, cast

from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic.fields import FieldInfo, PydanticUndefined

from jvspatial.core.entities import Walker

from .metadata import build_field_config, extract_field_metadata

# ============================================================================
# Base Parameter Model
# ============================================================================


class EndpointParameterModel(BaseModel):
    """Base model for endpoint parameters."""

    model_config = ConfigDict(extra="forbid")

    # Always include start_node parameter
    start_node: Optional[str] = Field(
        default=None,
        description="Starting node ID for graph traversal",
        examples=["n:Root:root"],
    )


class ParameterModelFactory:
    """Factory for creating parameter models from Walker classes and functions using Field metadata."""

    @classmethod
    def create_model(
        cls: Type["ParameterModelFactory"],
        target: Union[Type[Walker], Callable],
        path: Optional[str] = None,
    ) -> Optional[Type[BaseModel]]:
        """Create parameter model for a Walker class or function.

        Args:
            target: Walker class or function to create model for

        Returns:
            Generated parameter model
        """
        fields: Dict[str, Tuple[Any, Any]] = {}
        grouped_fields: Dict[str, List[Any]] = defaultdict(list)

        if inspect.isclass(target) and issubclass(target, Walker):
            # Handle Walker class
            return cls._create_walker_model(target, fields, grouped_fields)
        elif inspect.isfunction(target) or inspect.ismethod(target):
            # Handle function - pass path to exclude path parameters
            return cls._create_function_model(target, fields, grouped_fields, path=path)
        else:
            raise ValueError(f"Unsupported target type: {type(target)}")

    @classmethod
    def _create_walker_model(
        cls: Type["ParameterModelFactory"],
        walker_cls: Type[Walker],
        fields: Dict[str, Tuple[Any, Any]],
        grouped_fields: Dict[str, List[Tuple[str, Tuple[Any, Any]]]],
    ) -> Type[BaseModel]:
        """Create parameter model for Walker class."""
        # Walker base fields that should be excluded
        walker_base_fields = {
            "id",
            "queue",
            "response",
            "current_node",
            "paused",
            "type_code",
        }

        # Fields that should always be excluded (private attributes)
        private_fields = {
            name for name in walker_cls.model_fields.keys() if name.startswith("_")
        }

        for name, field_info in walker_cls.model_fields.items():
            endpoint_config = extract_field_metadata(field_info)

            # Skip private fields, base fields, and explicitly excluded fields
            if (
                name in private_fields
                or (name in walker_base_fields and not endpoint_config)
                or endpoint_config.get("exclude_endpoint", False)
            ):
                continue

            # Build field config - use endpoint config if available, otherwise create default
            if endpoint_config:
                param_name = endpoint_config.get("endpoint_name") or name
                field_tuple = cls._build_field(name, field_info, endpoint_config)
            else:
                # Create default field configuration for public properties
                param_name = name
                field_tuple = cls._build_default_field(name, field_info)

            # Handle field grouping
            group = endpoint_config.get("endpoint_group") if endpoint_config else None
            if group:
                grouped_fields[group].append((param_name, field_tuple))
            else:
                fields[param_name] = field_tuple

        # If no public properties found, return None to indicate no parameter model needed
        if not fields and not grouped_fields:
            return None

        # Create nested models for grouped fields
        for group_name, group_fields in grouped_fields.items():
            if group_fields:
                group_model = cls._create_group_model(group_name, group_fields)
                fields[group_name] = (Optional[group_model], Field(default=None))  # type: ignore[assignment]

        # Create the parameter model
        model_name = f"{walker_cls.__name__}ParameterModel"
        return cls._create_final_model(model_name, fields)

    @classmethod
    def _create_function_model(
        cls: Type["ParameterModelFactory"],
        func: Callable,
        fields: Dict[str, Tuple[Any, Any]],
        grouped_fields: Dict[str, List[Tuple[str, Tuple[Any, Any]]]],
        path: Optional[str] = None,
    ) -> Optional[Type[BaseModel]]:
        """Create parameter model for function."""
        import inspect
        import re
        from typing import get_type_hints

        # Get function signature
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)

        # Extract path parameters from path string (e.g., {user_id} from "/users/{user_id}")
        path_params = set()
        if path:
            # Find all {param} patterns in the path
            path_param_matches = re.findall(r"\{(\w+)\}", path)
            path_params = set(path_param_matches)

        # Skip 'self' parameter for methods
        params = {
            name: param for name, param in sig.parameters.items() if name != "self"
        }

        # Exclude path parameters from the model - FastAPI will handle them directly
        params = {
            name: param for name, param in params.items() if name not in path_params
        }

        # If no parameters remain (or none to begin with), return None
        if not params:
            return None

        for name, param in params.items():
            # Get type annotation
            param_type = type_hints.get(name, Any)

            # Check if parameter has a default value
            has_default = param.default != inspect.Parameter.empty

            # Get default value (only if parameter has one)
            if has_default:
                default = param.default
                # If type is Optional or Union with None, ensure param_type reflects that
                if default is None and param_type != Any:
                    # Check if already Optional
                    origin = getattr(param_type, "__origin__", None)
                    if origin is not Union:
                        param_type = Optional[param_type]
            else:
                # Parameter is required - use Field() without default
                # This makes it required in Pydantic, but we need to avoid PydanticUndefined in serialization
                # Use Ellipsis explicitly and ensure Field handles it correctly
                default = ...

            # Create field configuration
            field_config: Dict[str, Any] = {
                "description": f"{name.replace('_', ' ').title()} parameter",
                "title": name.replace("_", " ").title(),
            }

            # Add examples based on type
            if param_type == str:
                field_config["examples"] = ["example"]
            elif param_type == int:
                field_config["examples"] = [1]
            elif param_type == float:
                field_config["examples"] = [1.0]
            elif param_type == bool:
                field_config["examples"] = [True]
            elif param_type == list:
                field_config["examples"] = [[]]
            elif param_type == dict:
                field_config["examples"] = [{}]

            # For required fields, we need to handle them specially to avoid PydanticUndefined
            # We'll use a sentinel value and then validate that it's not None
            if default is ...:
                # Required field - make Optional with None default to avoid PydanticUndefined serialization
                # But we'll validate that None is not accepted in the wrapper
                if not cls._is_optional(param_type):
                    param_type = Optional[param_type]
                default = None

            # Extract only valid Field arguments - remove any custom keys
            valid_field_kwargs = {
                k: v
                for k, v in field_config.items()
                if k in ("description", "title", "examples", "json_schema_extra")
            }

            # Always pass explicit default to Field to avoid PydanticUndefined
            fields[name] = (param_type, Field(default=default, **valid_field_kwargs))

        # Create the parameter model
        model_name = f"{func.__name__}ParameterModel"
        return cls._create_final_model(model_name, fields)

    @classmethod
    def _create_final_model(
        cls: Type["ParameterModelFactory"],
        model_name: str,
        fields: Dict[str, Tuple[Any, Any]],
    ) -> Type[BaseModel]:
        """Create the final parameter model with examples."""
        # Create example data for the model
        example_data = {}
        for name, field_tuple in fields.items():
            field_type, field_info = field_tuple
            if hasattr(field_info, "default") and field_info.default is not None:
                example_data[name] = field_info.default
            elif hasattr(field_info, "examples") and field_info.examples:
                example_data[name] = field_info.examples[0]
            elif field_type == str:
                example_data[name] = "example"
            elif field_type == int:
                example_data[name] = 1
            elif field_type == bool:
                example_data[name] = True
            elif field_type == list:
                example_data[name] = []
            elif field_type == dict:
                example_data[name] = {}

        model = cast(
            Type[BaseModel],
            create_model(
                model_name,
                __base__=EndpointParameterModel,
                __config__=ConfigDict(extra="forbid"),
                **fields,
            ),
        )

        # Add example to the model
        model.model_config["json_schema_extra"] = {"example": example_data}

        return model

    @classmethod
    def _build_default_field(
        cls: Type["ParameterModelFactory"],
        name: str,
        field_info: FieldInfo,
    ) -> Tuple[Type, FieldInfo]:
        """Build a default field configuration for public properties.

        Args:
            name: Field name
            field_info: Original field info

        Returns:
            Tuple of (field_type, field_info)
        """
        # Get original type and default
        field_type = field_info.annotation
        default = field_info.default

        # Make field optional if it has a default value
        if default is not None and default != PydanticUndefined and default is not ...:
            if not cls._is_optional(field_type):
                field_type = Optional[field_type]
        elif default is PydanticUndefined or default is ...:
            # Required field - make it optional with None default for API flexibility
            # Convert PydanticUndefined to None for OpenAPI compatibility
            if not cls._is_optional(field_type):
                field_type = Optional[field_type]
            default = None

        # Create basic field configuration
        field_config: Dict[str, Any] = {
            "description": f"{name.replace('_', ' ').title()} parameter",
            "title": name.replace("_", " ").title(),
        }

        # Add examples based on type
        if field_type == str:
            field_config["examples"] = ["example"]
        elif field_type == int:
            field_config["examples"] = [1]
        elif field_type == bool:
            field_config["examples"] = [True]
        elif field_type == list:
            field_config["examples"] = [[]]
        elif field_type == dict:
            field_config["examples"] = [{}]
        elif hasattr(field_type, "__origin__") and field_type.__origin__ is Union:
            # Handle Union types
            args = getattr(field_type, "__args__", ())
            if str in args:
                field_config["examples"] = ["example"]
            elif int in args:
                field_config["examples"] = [1]
            elif bool in args:
                field_config["examples"] = [True]
            elif list in args:
                field_config["examples"] = [[]]
            elif dict in args:
                field_config["examples"] = [{}]

        # Ensure default is never PydanticUndefined or Ellipsis (convert to None for OpenAPI compatibility)
        if default is PydanticUndefined or default is ...:
            # For required fields, omit default from Field (makes it required in Pydantic)
            # But for API endpoints, we make it optional with None default for flexibility
            if not cls._is_optional(field_type):
                field_type = Optional[field_type]
            return (field_type, Field(default=None, **field_config))
        return (field_type, Field(default=default, **field_config))

    @classmethod
    def _build_field(
        cls: Type["ParameterModelFactory"],
        name: str,
        field_info: FieldInfo,
        endpoint_config: Dict[str, Any],
    ) -> Tuple[Type, FieldInfo]:
        """Build a parameter field.

        Args:
            name: Original field name
            field_info: Original field info
            endpoint_config: Endpoint configuration

        Returns:
            Tuple of (field_type, field_info)
        """
        # Get original type and default
        field_type = field_info.annotation
        default = field_info.default

        # Handle endpoint-specific required override
        if endpoint_config.get("endpoint_required") is not None:
            if endpoint_config["endpoint_required"]:
                # For required fields, use Ellipsis but only if we really need it
                # Otherwise, prefer None for API flexibility
                if default is None or default is PydanticUndefined:
                    # Use ... for truly required fields (but this might cause serialization issues)
                    # Better to make optional with None for API endpoints
                    default = None
                    if not cls._is_optional(field_type):
                        field_type = Optional[field_type]
            else:
                if not cls._is_optional(field_type):
                    field_type = Optional[field_type]
                if default is PydanticUndefined or default is ...:
                    default = None

        # Build field config
        config = build_field_config(field_info, endpoint_config)
        # Always convert PydanticUndefined or Ellipsis to None for OpenAPI compatibility
        # (PydanticUndefined and Ellipsis can't be serialized in OpenAPI schemas)
        if default is PydanticUndefined or default is ...:
            # Make field optional with None default for API flexibility
            if not cls._is_optional(field_type):
                field_type = Optional[field_type]
            default = None
        return (field_type, Field(default=default, **config))

    @classmethod
    def _create_group_model(
        cls: Type["ParameterModelFactory"],
        group_name: str,
        group_fields: List[Tuple[str, Tuple[Type, FieldInfo]]],
    ) -> Type[BaseModel]:
        """Create a model for grouped fields.

        Args:
            group_name: Name of the group
            group_fields: List of fields in the group

        Returns:
            Model class for the group
        """
        fields = dict(group_fields)
        model_name = f"{group_name.title()}Group"
        return cast(
            Type[BaseModel],
            create_model(
                model_name,
                __config__=ConfigDict(extra="forbid"),
                **fields,
            ),
        )

    @staticmethod
    def _is_optional(field_type: Type) -> bool:
        """Check if a type is Optional.

        Args:
            field_type: Type to check

        Returns:
            True if the type is Optional
        """
        return (
            hasattr(field_type, "__origin__")
            and field_type.__origin__ is Optional
            and type(None) in field_type.__args__
        )
