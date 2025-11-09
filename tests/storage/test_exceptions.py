"""Comprehensive test suite for storage exception classes.

Tests all custom exceptions for proper initialization, inheritance,
details population, message formatting, and exception handling.
"""

import pytest

from jvspatial.storage.exceptions import (
    AccessDeniedError,
    FileNotFoundError,
    FileSizeLimitError,
    InvalidMimeTypeError,
    InvalidPathError,
    PathTraversalError,
    StorageError,
    StorageProviderError,
    ValidationError,
)

# ============================================================================
# StorageError (Base Exception) Tests
# ============================================================================


class TestStorageError:
    """Tests for StorageError base exception."""

    async def test_init_with_message_only(self):
        """Test initialization with message only."""
        exc = StorageError("Test error")

        assert str(exc) == "Test error"
        assert exc.message == "Test error"
        assert exc.details == {}

    async def test_init_with_details(self):
        """Test initialization with details dictionary."""
        details = {"key": "value", "number": 42}
        exc = StorageError("Error with details", details=details)

        assert exc.message == "Error with details"
        assert exc.details == details
        assert exc.details["key"] == "value"
        assert exc.details["number"] == 42

    async def test_init_with_none_details(self):
        """Test that None details becomes empty dict."""
        exc = StorageError("Test", details=None)

        assert exc.details == {}

    async def test_inheritance_from_exception(self):
        """Test that StorageError inherits from Exception."""
        exc = StorageError("Test")

        assert isinstance(exc, Exception)

    async def test_can_be_raised_and_caught(self):
        """Test that exception can be raised and caught."""
        with pytest.raises(StorageError) as exc_info:
            raise StorageError("Test error")

        assert str(exc_info.value) == "Test error"

    async def test_empty_message(self):
        """Test with empty message string."""
        exc = StorageError("")

        assert exc.message == ""
        assert str(exc) == ""

    async def test_message_attribute(self):
        """Test that message is stored as attribute."""
        exc = StorageError("Custom message")

        assert hasattr(exc, "message")
        assert exc.message == "Custom message"

    async def test_details_attribute(self):
        """Test that details is stored as attribute."""
        exc = StorageError("Test", details={"a": 1})

        assert hasattr(exc, "details")
        assert isinstance(exc.details, dict)


# ============================================================================
# PathTraversalError Tests
# ============================================================================


class TestPathTraversalError:
    """Tests for PathTraversalError exception."""

    async def test_init_with_message_only(self):
        """Test initialization with message only."""
        exc = PathTraversalError("Path traversal detected")

        assert str(exc) == "Path traversal detected"
        assert exc.message == "Path traversal detected"
        assert exc.details == {}

    async def test_init_with_path(self):
        """Test initialization with path parameter."""
        exc = PathTraversalError("Dangerous path", path="../../../etc/passwd")

        assert exc.message == "Dangerous path"
        assert exc.details["path"] == "../../../etc/passwd"

    async def test_init_with_none_path(self):
        """Test initialization with None path."""
        exc = PathTraversalError("Error", path=None)

        assert exc.details == {}

    async def test_inherits_from_storage_error(self):
        """Test that PathTraversalError inherits from StorageError."""
        exc = PathTraversalError("Test")

        assert isinstance(exc, StorageError)
        assert isinstance(exc, Exception)

    async def test_can_be_raised_and_caught_as_storage_error(self):
        """Test can be caught as StorageError."""
        with pytest.raises(StorageError):
            raise PathTraversalError("Test")

    async def test_can_be_caught_specifically(self):
        """Test can be caught as PathTraversalError specifically."""
        with pytest.raises(PathTraversalError) as exc_info:
            raise PathTraversalError("Traversal attempt", path="../../file")

        assert exc_info.value.details["path"] == "../../file"

    async def test_string_representation(self):
        """Test string representation includes message."""
        exc = PathTraversalError("Security violation", path="/etc/passwd")

        assert "Security violation" in str(exc)


# ============================================================================
# InvalidPathError Tests
# ============================================================================


class TestInvalidPathError:
    """Tests for InvalidPathError exception."""

    async def test_init_with_message_only(self):
        """Test initialization with message only."""
        exc = InvalidPathError("Invalid path format")

        assert exc.message == "Invalid path format"
        assert exc.details == {}

    async def test_init_with_path(self):
        """Test initialization with path parameter."""
        exc = InvalidPathError("Path is invalid", path="invalid@path#$.txt")

        assert exc.details["path"] == "invalid@path#$.txt"

    async def test_init_with_none_path(self):
        """Test that None path results in empty details."""
        exc = InvalidPathError("Error", path=None)

        assert exc.details == {}

    async def test_inherits_from_storage_error(self):
        """Test inheritance from StorageError."""
        exc = InvalidPathError("Test")

        assert isinstance(exc, StorageError)

    async def test_empty_path_string(self):
        """Test with empty path string."""
        exc = InvalidPathError("Empty path", path="")

        # Empty string is falsy, so details will be empty
        assert exc.details == {}

    async def test_can_be_raised_and_caught(self):
        """Test exception can be raised and caught."""
        with pytest.raises(InvalidPathError) as exc_info:
            raise InvalidPathError("Bad path", path="file@$.txt")

        assert exc_info.value.details["path"] == "file@$.txt"


# ============================================================================
# ValidationError Tests
# ============================================================================


class TestValidationError:
    """Tests for ValidationError exception."""

    async def test_init_with_message_only(self):
        """Test initialization with message only."""
        exc = ValidationError("Validation failed")

        assert exc.message == "Validation failed"
        assert "validation_type" not in exc.details

    async def test_init_with_validation_type(self):
        """Test initialization with validation_type parameter."""
        exc = ValidationError("Failed", validation_type="mime")

        assert exc.details["validation_type"] == "mime"

    async def test_init_with_kwargs(self):
        """Test initialization with additional kwargs."""
        exc = ValidationError("Validation error", file_name="test.txt", error_code=123)

        assert exc.details["file_name"] == "test.txt"
        assert exc.details["error_code"] == 123

    async def test_init_with_validation_type_and_kwargs(self):
        """Test with both validation_type and kwargs."""
        exc = ValidationError(
            "Error", validation_type="size", actual_size=5000, max_size=1000
        )

        assert exc.details["validation_type"] == "size"
        assert exc.details["actual_size"] == 5000
        assert exc.details["max_size"] == 1000

    async def test_init_with_none_validation_type(self):
        """Test that None validation_type doesn't add to details."""
        exc = ValidationError("Error", validation_type=None)

        assert "validation_type" not in exc.details

    async def test_inherits_from_storage_error(self):
        """Test inheritance from StorageError."""
        exc = ValidationError("Test")

        assert isinstance(exc, StorageError)

    async def test_kwargs_are_stored_in_details(self):
        """Test that all kwargs are stored in details."""
        exc = ValidationError("Error", key1="value1", key2="value2", key3=42)

        assert exc.details["key1"] == "value1"
        assert exc.details["key2"] == "value2"
        assert exc.details["key3"] == 42


# ============================================================================
# FileNotFoundError Tests
# ============================================================================


class TestFileNotFoundError:
    """Tests for FileNotFoundError exception."""

    async def test_init_with_message_only(self):
        """Test initialization with message only."""
        exc = FileNotFoundError("File not found")

        assert exc.message == "File not found"
        assert exc.details == {}

    async def test_init_with_file_path(self):
        """Test initialization with file_path parameter."""
        exc = FileNotFoundError("Missing file", file_path="uploads/doc.pdf")

        assert exc.details["file_path"] == "uploads/doc.pdf"

    async def test_init_with_none_file_path(self):
        """Test that None file_path results in empty details."""
        exc = FileNotFoundError("Error", file_path=None)

        assert exc.details == {}

    async def test_inherits_from_storage_error(self):
        """Test inheritance from StorageError."""
        exc = FileNotFoundError("Test")

        assert isinstance(exc, StorageError)

    async def test_can_be_raised_and_caught(self):
        """Test exception can be raised and caught."""
        with pytest.raises(FileNotFoundError) as exc_info:
            raise FileNotFoundError("Not found", file_path="missing.txt")

        assert exc_info.value.details["file_path"] == "missing.txt"

    async def test_empty_file_path(self):
        """Test with empty file_path string."""
        exc = FileNotFoundError("Error", file_path="")

        # Empty string is falsy, so details will be empty
        assert exc.details == {}


# ============================================================================
# FileSizeLimitError Tests
# ============================================================================


class TestFileSizeLimitError:
    """Tests for FileSizeLimitError exception."""

    async def test_init_with_message_only(self):
        """Test initialization with message only."""
        exc = FileSizeLimitError("File too large")

        assert exc.message == "File too large"
        assert exc.details["validation_type"] == "size"

    async def test_init_with_file_size(self):
        """Test initialization with file_size parameter."""
        exc = FileSizeLimitError("Too large", file_size=5000000)

        assert exc.details["file_size"] == 5000000
        assert exc.details["validation_type"] == "size"

    async def test_init_with_max_size(self):
        """Test initialization with max_size parameter."""
        exc = FileSizeLimitError("Too large", max_size=1000000)

        assert exc.details["max_size"] == 1000000

    async def test_init_with_both_sizes(self):
        """Test initialization with both file_size and max_size."""
        exc = FileSizeLimitError("Exceeds limit", file_size=5000000, max_size=1000000)

        assert exc.details["file_size"] == 5000000
        assert exc.details["max_size"] == 1000000

    async def test_init_with_none_values(self):
        """Test initialization with None size values."""
        exc = FileSizeLimitError("Error", file_size=None, max_size=None)

        assert exc.details["file_size"] is None
        assert exc.details["max_size"] is None

    async def test_inherits_from_validation_error(self):
        """Test that FileSizeLimitError inherits from ValidationError."""
        exc = FileSizeLimitError("Test")

        assert isinstance(exc, ValidationError)
        assert isinstance(exc, StorageError)

    async def test_validation_type_is_size(self):
        """Test that validation_type is automatically set to 'size'."""
        exc = FileSizeLimitError("Test")

        assert exc.details["validation_type"] == "size"

    async def test_can_be_caught_as_validation_error(self):
        """Test can be caught as ValidationError."""
        with pytest.raises(ValidationError):
            raise FileSizeLimitError("Too big")


# ============================================================================
# InvalidMimeTypeError Tests
# ============================================================================


class TestInvalidMimeTypeError:
    """Tests for InvalidMimeTypeError exception."""

    async def test_init_with_message_only(self):
        """Test initialization with message only."""
        exc = InvalidMimeTypeError("Invalid MIME type")

        assert exc.message == "Invalid MIME type"
        assert exc.details["validation_type"] == "mime_type"

    async def test_init_with_detected_type(self):
        """Test initialization with detected_type parameter."""
        exc = InvalidMimeTypeError(
            "Wrong type", detected_type="application/x-executable"
        )

        assert exc.details["detected_type"] == "application/x-executable"

    async def test_init_with_expected_type(self):
        """Test initialization with expected_type parameter."""
        exc = InvalidMimeTypeError("Mismatch", expected_type="image/jpeg")

        assert exc.details["expected_type"] == "image/jpeg"

    async def test_init_with_both_types(self):
        """Test initialization with both detected and expected types."""
        exc = InvalidMimeTypeError(
            "Type mismatch", detected_type="text/plain", expected_type="application/pdf"
        )

        assert exc.details["detected_type"] == "text/plain"
        assert exc.details["expected_type"] == "application/pdf"

    async def test_init_with_none_values(self):
        """Test initialization with None type values."""
        exc = InvalidMimeTypeError("Error", detected_type=None, expected_type=None)

        assert exc.details["detected_type"] is None
        assert exc.details["expected_type"] is None

    async def test_inherits_from_validation_error(self):
        """Test inheritance from ValidationError."""
        exc = InvalidMimeTypeError("Test")

        assert isinstance(exc, ValidationError)
        assert isinstance(exc, StorageError)

    async def test_validation_type_is_mime_type(self):
        """Test that validation_type is automatically set to 'mime_type'."""
        exc = InvalidMimeTypeError("Test")

        assert exc.details["validation_type"] == "mime_type"

    async def test_can_be_raised_and_caught(self):
        """Test exception can be raised and caught."""
        with pytest.raises(InvalidMimeTypeError) as exc_info:
            raise InvalidMimeTypeError(
                "Bad MIME", detected_type="application/x-sh", expected_type="text/plain"
            )

        assert exc_info.value.details["detected_type"] == "application/x-sh"


# ============================================================================
# StorageProviderError Tests
# ============================================================================


class TestStorageProviderError:
    """Tests for StorageProviderError exception."""

    async def test_init_with_message_only(self):
        """Test initialization with message only."""
        exc = StorageProviderError("Provider error")

        assert exc.message == "Provider error"
        assert exc.details["provider"] is None
        assert exc.details["operation"] is None

    async def test_init_with_provider(self):
        """Test initialization with provider parameter."""
        exc = StorageProviderError("Error", provider="s3")

        assert exc.details["provider"] == "s3"

    async def test_init_with_operation(self):
        """Test initialization with operation parameter."""
        exc = StorageProviderError("Error", operation="save")

        assert exc.details["operation"] == "save"

    async def test_init_with_both_parameters(self):
        """Test initialization with both provider and operation."""
        exc = StorageProviderError("S3 save failed", provider="s3", operation="save")

        assert exc.details["provider"] == "s3"
        assert exc.details["operation"] == "save"

    async def test_init_with_none_values(self):
        """Test that None values are stored in details."""
        exc = StorageProviderError("Error", provider=None, operation=None)

        assert "provider" in exc.details
        assert "operation" in exc.details
        assert exc.details["provider"] is None
        assert exc.details["operation"] is None

    async def test_inherits_from_storage_error(self):
        """Test inheritance from StorageError."""
        exc = StorageProviderError("Test")

        assert isinstance(exc, StorageError)

    async def test_various_provider_names(self):
        """Test with various provider names."""
        providers = ["local", "s3", "azure", "gcp"]

        for provider in providers:
            exc = StorageProviderError("Error", provider=provider)
            assert exc.details["provider"] == provider

    async def test_various_operations(self):
        """Test with various operation names."""
        operations = ["save", "get", "delete", "list", "init"]

        for op in operations:
            exc = StorageProviderError("Error", operation=op)
            assert exc.details["operation"] == op


# ============================================================================
# AccessDeniedError Tests
# ============================================================================


class TestAccessDeniedError:
    """Tests for AccessDeniedError exception."""

    async def test_init_with_message_only(self):
        """Test initialization with message only."""
        exc = AccessDeniedError("Access denied")

        assert exc.message == "Access denied"
        assert exc.details == {}

    async def test_init_with_file_path(self):
        """Test initialization with file_path parameter."""
        exc = AccessDeniedError("Forbidden", file_path="private/secret.txt")

        assert exc.details["file_path"] == "private/secret.txt"

    async def test_init_with_none_file_path(self):
        """Test that None file_path results in empty details."""
        exc = AccessDeniedError("Error", file_path=None)

        assert exc.details == {}

    async def test_inherits_from_storage_error(self):
        """Test inheritance from StorageError."""
        exc = AccessDeniedError("Test")

        assert isinstance(exc, StorageError)

    async def test_can_be_raised_and_caught(self):
        """Test exception can be raised and caught."""
        with pytest.raises(AccessDeniedError) as exc_info:
            raise AccessDeniedError("Denied", file_path="admin/config.txt")

        assert exc_info.value.details["file_path"] == "admin/config.txt"

    async def test_empty_file_path(self):
        """Test with empty file_path string."""
        exc = AccessDeniedError("Error", file_path="")

        # Empty string is falsy, so details will be empty
        assert exc.details == {}


# ============================================================================
# Exception Chaining and Context Tests
# ============================================================================


class TestExceptionChaining:
    """Tests for exception chaining and context."""

    async def test_raise_from_another_exception(self):
        """Test raising storage exception from another exception."""
        try:
            try:
                raise ValueError("Original error")
            except ValueError as e:
                raise StorageError("Storage failed") from e
        except StorageError as exc:
            assert exc.__cause__ is not None
            assert isinstance(exc.__cause__, ValueError)

    async def test_exception_context_preserved(self):
        """Test that exception context is preserved."""
        try:
            try:
                raise IOError("IO failed")
            except IOError:
                raise PathTraversalError("Path error", path="/etc/passwd")
        except PathTraversalError as exc:
            assert exc.__context__ is not None
            assert isinstance(exc.__context__, IOError)

    async def test_nested_exception_handling(self):
        """Test nested exception handling."""
        with pytest.raises(StorageError):
            try:
                raise ValidationError("Inner error")
            except ValidationError:
                raise StorageProviderError("Outer error", provider="s3")


# ============================================================================
# Exception Attributes and Methods Tests
# ============================================================================


class TestExceptionAttributes:
    """Tests for exception attributes and methods."""

    async def test_all_exceptions_have_message(self):
        """Test that all exceptions have message attribute."""
        exceptions = [
            StorageError("test"),
            PathTraversalError("test"),
            InvalidPathError("test"),
            ValidationError("test"),
            FileNotFoundError("test"),
            FileSizeLimitError("test"),
            InvalidMimeTypeError("test"),
            StorageProviderError("test"),
            AccessDeniedError("test"),
        ]

        for exc in exceptions:
            assert hasattr(exc, "message")
            assert exc.message == "test"

    async def test_all_exceptions_have_details(self):
        """Test that all exceptions have details attribute."""
        exceptions = [
            StorageError("test"),
            PathTraversalError("test"),
            InvalidPathError("test"),
            ValidationError("test"),
            FileNotFoundError("test"),
            FileSizeLimitError("test"),
            InvalidMimeTypeError("test"),
            StorageProviderError("test"),
            AccessDeniedError("test"),
        ]

        for exc in exceptions:
            assert hasattr(exc, "details")
            assert isinstance(exc.details, dict)

    async def test_string_representation_includes_message(self):
        """Test that str() includes the message."""
        exc = StorageError("Custom error message")

        assert "Custom error message" in str(exc)

    async def test_repr_is_valid(self):
        """Test that repr() returns valid representation."""
        exc = StorageError("Test error")

        repr_str = repr(exc)
        assert repr_str is not None
        assert isinstance(repr_str, str)


# ============================================================================
# Exception Usage in Try/Except Blocks Tests
# ============================================================================


class TestExceptionUsage:
    """Tests for using exceptions in try/except blocks."""

    async def test_catch_specific_exception(self):
        """Test catching specific exception type."""
        with pytest.raises(PathTraversalError):
            raise PathTraversalError("Test", path="../../etc")

    async def test_catch_base_exception(self):
        """Test catching via base StorageError."""
        with pytest.raises(StorageError):
            raise FileSizeLimitError("Test")

    async def test_multiple_exception_types(self):
        """Test catching multiple exception types."""
        for exc_class in [PathTraversalError, InvalidPathError, ValidationError]:
            with pytest.raises(StorageError):
                raise exc_class("Test")

    async def test_exception_info_captured(self):
        """Test that exception info is properly captured."""
        with pytest.raises(FileSizeLimitError) as exc_info:
            raise FileSizeLimitError("File too large", file_size=10000, max_size=5000)

        assert exc_info.value.details["file_size"] == 10000
        assert exc_info.value.details["max_size"] == 5000
        assert exc_info.value.message == "File too large"


# ============================================================================
# Edge Cases and Special Scenarios Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    async def test_exception_with_very_long_message(self):
        """Test exception with very long message."""
        long_message = "x" * 10000
        exc = StorageError(long_message)

        assert exc.message == long_message
        assert len(str(exc)) == 10000

    async def test_exception_with_unicode_message(self):
        """Test exception with unicode characters in message."""
        exc = StorageError("Error: 文件未找到 🚫")

        assert "文件未找到" in exc.message
        assert "🚫" in exc.message

    async def test_exception_with_special_characters(self):
        """Test exception with special characters."""
        exc = StorageError("Error: <>&\"'")

        assert exc.message == "Error: <>&\"'"

    async def test_exception_with_newlines_in_message(self):
        """Test exception with newlines in message."""
        exc = StorageError("Line 1\nLine 2\nLine 3")

        assert "\n" in exc.message
        assert exc.message.count("\n") == 2

    async def test_details_with_complex_data_types(self):
        """Test details dictionary with complex data types."""
        details = {
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
            "tuple": (1, 2),
            "none": None,
            "bool": True,
        }
        exc = StorageError("Test", details=details)

        assert exc.details["list"] == [1, 2, 3]
        assert exc.details["dict"] == {"nested": "value"}
        assert exc.details["tuple"] == (1, 2)
        assert exc.details["none"] is None
        assert exc.details["bool"] is True

    async def test_exception_with_empty_details(self):
        """Test exception with explicitly empty details."""
        exc = StorageError("Test", details={})

        assert exc.details == {}

    async def test_modifying_details_after_creation(self):
        """Test that details can be modified after exception creation."""
        exc = StorageError("Test")
        exc.details["new_key"] = "new_value"

        assert exc.details["new_key"] == "new_value"


# ============================================================================
# Module Imports and Availability Tests
# ============================================================================


async def test_all_exceptions_importable():
    """Test that all exceptions can be imported."""
    from jvspatial.storage.exceptions import (
        AccessDeniedError,
        FileNotFoundError,
        FileSizeLimitError,
        InvalidMimeTypeError,
        InvalidPathError,
        PathTraversalError,
        StorageError,
        StorageProviderError,
        ValidationError,
    )

    # All imports successful
    assert StorageError is not None
    assert PathTraversalError is not None
    assert InvalidPathError is not None
    assert ValidationError is not None
    assert FileNotFoundError is not None
    assert FileSizeLimitError is not None
    assert InvalidMimeTypeError is not None
    assert StorageProviderError is not None
    assert AccessDeniedError is not None


async def test_exceptions_available_from_main_module():
    """Test that exceptions are available from main storage module."""
    from jvspatial.storage import (
        AccessDeniedError,
        FileNotFoundError,
        FileSizeLimitError,
        InvalidMimeTypeError,
        InvalidPathError,
        PathTraversalError,
        StorageError,
        StorageProviderError,
        ValidationError,
    )

    # All should be importable from main module
    assert all(
        [
            StorageError,
            PathTraversalError,
            InvalidPathError,
            ValidationError,
            FileNotFoundError,
            FileSizeLimitError,
            InvalidMimeTypeError,
            StorageProviderError,
            AccessDeniedError,
        ]
    )
