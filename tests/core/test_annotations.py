import pytest
from pydantic import BaseModel, Field

from jvspatial.core.annotations import (
    ProtectedAttributeMixin,
    private,
    protected,
    transient,
)


def test_private_annotation():
    """Test that private attributes are excluded from serialization."""

    class TestModel(ProtectedAttributeMixin, BaseModel):
        public_field: str
        _private_field: str = private(default="secret")
        protected_field: str = protected("protected")
        transient_field: str = transient("temp")

    instance = TestModel(public_field="public")

    # Access works normally
    assert instance._private_field == "secret"

    # Not included in serialization (private attrs are Pydantic private)
    model_dump = instance.model_dump()
    assert "public_field" in model_dump
    assert "_private_field" not in model_dump
    assert "protected_field" in model_dump
    assert "transient_field" in model_dump

    # Not included in database representation
    model_export = instance.export()  # ProtectedAttributeMixin provides export()
    assert "_private_field" not in model_export


def test_compound_private_transient():
    """Test that private attributes work correctly."""

    class TestModel(ProtectedAttributeMixin, BaseModel):
        _internal_cache: dict = private(default_factory=dict)

    instance = TestModel()
    instance._internal_cache["key"] = "value"

    # Not included in any serialization (private attrs excluded automatically)
    assert "_internal_cache" not in instance.model_dump()
    assert "_internal_cache" not in instance.export()


def test_private_with_metadata():
    """Test private annotation works as Pydantic PrivateAttr."""

    class TestModel(BaseModel):
        _counter: int = private(default=0)

    instance = TestModel()
    assert instance._counter == 0

    # Private attrs are not in model_fields (they're private attrs)
    assert "_counter" not in TestModel.model_fields
    # But they exist as private attributes
    assert hasattr(instance, "_counter")
