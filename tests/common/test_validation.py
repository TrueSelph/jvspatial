"""Test suite for common validation utilities."""

import pytest

from jvspatial.common.validation import PathValidator


class TestPathValidator:
    """Test PathValidator functionality."""

    def test_is_valid_id_valid(self):
        """Test valid ID validation."""
        assert PathValidator.is_valid_id("test_id") is True
        assert PathValidator.is_valid_id("test-id") is True
        assert PathValidator.is_valid_id("test_id_123") is True
        assert PathValidator.is_valid_id("test:id") is True

    def test_is_valid_id_invalid(self):
        """Test invalid ID validation."""
        assert PathValidator.is_valid_id("") is False
        assert PathValidator.is_valid_id("test id") is False  # Space not allowed
        assert PathValidator.is_valid_id("test@id") is False  # @ not allowed
        assert PathValidator.is_valid_id("test.id") is False  # . not allowed

    def test_is_valid_collection_name_valid(self):
        """Test valid collection name validation."""
        assert PathValidator.is_valid_collection_name("test") is True
        assert PathValidator.is_valid_collection_name("test_collection") is True
        assert PathValidator.is_valid_collection_name("test-collection") is True
        assert PathValidator.is_valid_collection_name("test123") is True

    def test_is_valid_collection_name_invalid(self):
        """Test invalid collection name validation."""
        assert PathValidator.is_valid_collection_name("") is False
        assert (
            PathValidator.is_valid_collection_name("123test") is False
        )  # Must start with letter
        assert (
            PathValidator.is_valid_collection_name("test collection") is False
        )  # Space not allowed
        assert (
            PathValidator.is_valid_collection_name("test@collection") is False
        )  # @ not allowed
