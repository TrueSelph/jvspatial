"""Field metadata extraction and handling for endpoint parameters."""

from typing import Any, Dict

from pydantic.fields import FieldInfo


def extract_field_metadata(field_info: FieldInfo) -> Dict[str, Any]:
    """Extract endpoint configuration from field metadata.

    Args:
        field_info: Pydantic field info object

    Returns:
        Dictionary of endpoint configuration
    """
    json_schema_extra = getattr(field_info, "json_schema_extra", None)

    if callable(json_schema_extra):
        try:
            schema: Dict[str, Any] = {}
            json_schema_extra(schema, type(None))
            config: Dict[str, Any] = schema.get("endpoint_config", {}) or {}
            return config
        except Exception:
            return {}
    elif isinstance(json_schema_extra, dict):
        endpoint_config: Dict[str, Any] = (
            json_schema_extra.get("endpoint_config", {}) or {}
        )
        return endpoint_config

    return {}


def build_field_config(
    field_info: FieldInfo,
    endpoint_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Build field configuration from field info and endpoint config.

    Args:
        field_info: Original field info
        endpoint_config: Endpoint-specific configuration

    Returns:
        Field configuration dictionary
    """
    config = {
        "title": field_info.title,
        "description": field_info.description,
    }

    # Add examples if available
    if hasattr(field_info, "examples") and field_info.examples:
        config["examples"] = field_info.examples

    # Add validation constraints
    if hasattr(field_info, "metadata") and field_info.metadata:
        for constraint in field_info.metadata:
            for name in [
                "gt",
                "ge",
                "lt",
                "le",
                "min_length",
                "max_length",
                "pattern",
            ]:
                if hasattr(constraint, name):
                    config[name] = getattr(constraint, name)

    # Add endpoint constraints
    config.update(endpoint_config.get("endpoint_constraints", {}))

    # Add OpenAPI config
    if (
        endpoint_config.get("endpoint_deprecated")
        or endpoint_config.get("endpoint_hidden")
        or endpoint_config.get("endpoint_constraints")
    ):

        def schema_extra(schema: Dict[str, Any], _: type) -> None:
            if endpoint_config.get("endpoint_deprecated"):
                schema["deprecated"] = True
            if endpoint_config.get("endpoint_hidden"):
                schema["writeOnly"] = True
            for key, value in endpoint_config.get("endpoint_constraints", {}).items():
                if key not in schema:
                    schema[key] = value

        config["json_schema_extra"] = schema_extra

    return {k: v for k, v in config.items() if v is not None}
