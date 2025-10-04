"""Comprehensive test suite for attribute annotation system.

Tests @protected, @transient, and @private decorators and their combinations.
"""

import pytest
from pydantic import BaseModel, Field

from jvspatial.core.annotations import (
    AttributeProtectionError,
    ProtectedAttributeMixin,
    get_protected_attrs,
    get_transient_attrs,
    is_protected,
    is_transient,
    private,
    protected,
    transient,
)


class SampleEntity(ProtectedAttributeMixin, BaseModel):
    """Sample entity for annotation testing."""

    # Protected field - cannot be modified after initialization
    id: str = protected("", description="Unique identifier")

    # Normal field - can be modified
    name: str = "Test Entity"

    # Transient field - excluded from exports
    cache: dict = transient(Field(default_factory=dict), description="Temporary cache")

    # Both protected and transient using compound decorators
    internal_state: dict = protected(transient(Field(default_factory=dict)))


class TestPrivateAnnotation:
    """Tests for @private decorator functionality (Pydantic PrivateAttr)."""

    def test_private_annotation(self):
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

    def test_compound_private_transient(self):
        """Test that private attributes work correctly."""

        class TestModel(ProtectedAttributeMixin, BaseModel):
            _internal_cache: dict = private(default_factory=dict)

        instance = TestModel()
        instance._internal_cache["key"] = "value"

        # Not included in any serialization (private attrs excluded automatically)
        assert "_internal_cache" not in instance.model_dump()
        assert "_internal_cache" not in instance.export()

    def test_private_with_metadata(self):
        """Test private annotation works as Pydantic PrivateAttr."""

        class TestModel(BaseModel):
            _counter: int = private(default=0)

        instance = TestModel()
        assert instance._counter == 0

        # Private attrs are not in model_fields (they're private attrs)
        assert "_counter" not in TestModel.model_fields
        # But they exist as private attributes
        assert hasattr(instance, "_counter")


class TestProtectedAnnotation:
    """Tests for @protected decorator functionality."""

    def test_protected_field_initialization(self):
        """Test that protected fields can be set during initialization."""
        entity = SampleEntity(id="test-123", name="My Entity")
        assert entity.id == "test-123"
        assert entity.name == "My Entity"

    def test_normal_field_modification(self):
        """Test that normal fields can be modified after initialization."""
        entity = SampleEntity(id="test-123")
        entity.name = "Updated Name"
        assert entity.name == "Updated Name"

    def test_protected_field_modification_fails(self):
        """Test that protected fields cannot be modified after initialization."""
        entity = SampleEntity(id="test-123", name="My Entity")

        with pytest.raises(AttributeProtectionError) as exc_info:
            entity.id = "new-id"

        assert exc_info.value.attr_name == "id"
        assert exc_info.value.cls_name == "SampleEntity"
        assert "Cannot modify protected attribute" in str(exc_info.value)

    def test_is_protected_utility(self):
        """Test is_protected utility function."""
        assert is_protected(SampleEntity, "id") is True
        assert is_protected(SampleEntity, "name") is False
        assert is_protected(SampleEntity, "cache") is False

    def test_get_protected_attrs_utility(self):
        """Test get_protected_attrs utility function."""
        protected_attrs = get_protected_attrs(SampleEntity)
        assert "id" in protected_attrs
        assert "internal_state" in protected_attrs
        assert "name" not in protected_attrs


class TestTransientAnnotation:
    """Tests for @transient decorator functionality."""

    def test_transient_field_works_at_runtime(self):
        """Test that transient fields work normally at runtime."""
        entity = SampleEntity(id="test-456", name="Transient Test")
        entity.cache["temp_data"] = "should not be exported"
        entity.internal_state["secret"] = (
            "also should not be exported"  # pragma: allowlist secret
        )

        assert entity.cache["temp_data"] == "should not be exported"
        assert (
            entity.internal_state["secret"]
            == "also should not be exported"  # pragma: allowlist secret
        )

    def test_transient_field_excluded_from_export(self):
        """Test that transient fields are excluded from exports."""
        entity = SampleEntity(id="test-456", name="Transient Test")
        entity.cache["temp_data"] = "should not be exported"

        export_data = entity.export()

        # Verify transient fields are excluded
        assert "cache" not in export_data
        assert "internal_state" not in export_data

        # Verify normal fields are included
        assert export_data.get("id") == "test-456"
        assert export_data.get("name") == "Transient Test"

    def test_is_transient_utility(self):
        """Test is_transient utility function."""
        assert is_transient(SampleEntity, "cache") is True
        assert is_transient(SampleEntity, "internal_state") is True
        assert is_transient(SampleEntity, "id") is False
        assert is_transient(SampleEntity, "name") is False

    def test_get_transient_attrs_utility(self):
        """Test get_transient_attrs utility function."""
        transient_attrs = get_transient_attrs(SampleEntity)
        assert "cache" in transient_attrs
        assert "internal_state" in transient_attrs
        assert "id" not in transient_attrs


class TestCompoundDecorators:
    """Tests for compound @protected @transient usage."""

    def test_compound_protection_works(self):
        """Test that compound decorators provide protection."""
        entity = SampleEntity(id="test-789")
        entity.internal_state["data"] = "test"

        # Should be protected (cannot replace dict)
        with pytest.raises(AttributeProtectionError):
            entity.internal_state = {"new": "dict"}

    def test_compound_transient_works(self):
        """Test that compound decorators exclude from export."""
        entity = SampleEntity(id="test-789")
        entity.internal_state["data"] = "test"

        export_data = entity.export()

        # Should be transient (not in export)
        assert "internal_state" not in export_data

    def test_compound_both_behaviors(self):
        """Test that compound decorators have both behaviors."""
        entity = SampleEntity(id="test-789")

        # Verify it's both protected and transient
        assert is_protected(SampleEntity, "internal_state")
        assert is_transient(SampleEntity, "internal_state")


class TestInheritance:
    """Tests for annotation inheritance across class hierarchy."""

    def test_inherited_annotations(self):
        """Test that annotations work with inheritance."""

        class ParentEntity(ProtectedAttributeMixin, BaseModel):
            """Parent entity with annotations."""

            parent_id: str = protected("", description="Parent identifier")
            parent_cache: dict = transient(Field(default_factory=dict))

        class ChildEntity(ParentEntity):
            """Child entity with additional annotations."""

            child_id: str = protected("child-default", description="Child identifier")
            child_cache: list = transient(
                Field(default_factory=list), description="Child cache"
            )

        # Create child entity
        child = ChildEntity(parent_id="parent-123", child_id="child-456")
        child.parent_cache["item"] = "value"
        child.child_cache.append("temp_item")

        # Test parent protection
        with pytest.raises(AttributeProtectionError):
            child.parent_id = "new-parent-id"

        # Test child protection
        with pytest.raises(AttributeProtectionError):
            child.child_id = "new-child-id"

        # Test export excludes both transient fields
        export_data = child.export()
        assert "parent_cache" not in export_data
        assert "child_cache" not in export_data
        assert export_data.get("parent_id") == "parent-123"
        assert export_data.get("child_id") == "child-456"

    def test_protected_attrs_includes_inherited(self):
        """Test that get_protected_attrs includes inherited fields."""

        class Parent(ProtectedAttributeMixin, BaseModel):
            parent_field: str = protected("")

        class Child(Parent):
            child_field: str = protected("")

        protected_attrs = get_protected_attrs(Child)
        assert "parent_field" in protected_attrs
        assert "child_field" in protected_attrs

    def test_transient_attrs_includes_inherited(self):
        """Test that get_transient_attrs includes inherited fields."""

        class Parent(ProtectedAttributeMixin, BaseModel):
            parent_cache: dict = transient(Field(default_factory=dict))

        class Child(Parent):
            child_cache: dict = transient(Field(default_factory=dict))

        transient_attrs = get_transient_attrs(Child)
        assert "parent_cache" in transient_attrs
        assert "child_cache" in transient_attrs


class TestPrivateDecorator:
    """Tests for @private decorator functionality."""

    def test_private_creates_pydantic_private_attributes(self):
        """Test that private decorator creates Pydantic private attributes (underscore fields)."""

        class Entity(ProtectedAttributeMixin, BaseModel):
            id: str = protected("")
            _internal: dict = private(default_factory=dict)

        entity = Entity(id="test")
        entity._internal["key"] = "value"

        # Private attrs are excluded from model_dump automatically
        assert "_internal" not in entity.model_dump()

        # Private attrs are also excluded from export
        export_data = entity.export()
        assert "_internal" not in export_data

        # For non-underscore fields needing protection + transient, use compound syntax
        class EntityWithCompound(ProtectedAttributeMixin, BaseModel):
            id: str = protected("")
            internal: dict = protected(transient(Field(default_factory=dict)))

        entity2 = EntityWithCompound(id="test2")
        entity2.internal["key"] = "value"

        # Should be protected
        with pytest.raises(AttributeProtectionError):
            entity2.internal = {}

        # Should be transient
        export_data2 = entity2.export()
        assert "internal" not in export_data2

        # Verify both flags
        assert is_protected(EntityWithCompound, "internal")
        assert is_transient(EntityWithCompound, "internal")


class TestFieldWithDefaultFactory:
    """Tests for proper handling of Field with default_factory."""

    def test_transient_with_default_factory_dict(self):
        """Test transient with dict default_factory."""

        class Entity(ProtectedAttributeMixin, BaseModel):
            cache: dict = transient(Field(default_factory=dict))

        entity = Entity()
        assert isinstance(entity.cache, dict)
        entity.cache["key"] = "value"
        assert entity.cache["key"] == "value"

    def test_transient_with_default_factory_list(self):
        """Test transient with list default_factory."""

        class Entity(ProtectedAttributeMixin, BaseModel):
            items: list = transient(Field(default_factory=list))

        entity = Entity()
        assert isinstance(entity.items, list)
        entity.items.append("item")
        assert len(entity.items) == 1

    def test_field_with_additional_kwargs(self):
        """Test that additional kwargs are preserved with Field."""

        class Entity(ProtectedAttributeMixin, BaseModel):
            cache: dict = transient(
                Field(default_factory=dict), description="Test cache"
            )

        # Should work without validation errors
        entity = Entity()
        assert isinstance(entity.cache, dict)


class TestErrorMessages:
    """Tests for error message quality."""

    def test_protection_error_message_quality(self):
        """Test that AttributeProtectionError provides useful information."""
        entity = SampleEntity(id="test-123")

        with pytest.raises(AttributeProtectionError) as exc_info:
            entity.id = "new-id"

        error = exc_info.value
        assert error.attr_name == "id"
        assert error.cls_name == "SampleEntity"
        assert "id" in str(error)
        assert "SampleEntity" in str(error)
        assert "after initialization" in str(error)


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_setting_protected_field_to_same_value(self):
        """Test that setting a protected field to its current value still fails."""
        entity = SampleEntity(id="test-123")

        with pytest.raises(AttributeProtectionError):
            entity.id = "test-123"  # Same value, still protected

    def test_multiple_protected_fields(self):
        """Test entity with multiple protected fields."""

        class MultiProtected(ProtectedAttributeMixin, BaseModel):
            id: str = protected("")
            uuid: str = protected("")
            created_at: str = protected("")

        entity = MultiProtected(id="1", uuid="abc", created_at="2024-01-01")

        # All should be protected
        with pytest.raises(AttributeProtectionError):
            entity.id = "new"
        with pytest.raises(AttributeProtectionError):
            entity.uuid = "new"
        with pytest.raises(AttributeProtectionError):
            entity.created_at = "new"

    def test_empty_entity(self):
        """Test entity with no annotations."""

        class EmptyEntity(ProtectedAttributeMixin, BaseModel):
            name: str = ""

        entity = EmptyEntity(name="test")
        entity.name = "updated"  # Should work
        assert entity.name == "updated"

        # No protected or transient fields
        assert len(get_protected_attrs(EmptyEntity)) == 0
        assert len(get_transient_attrs(EmptyEntity)) == 0
