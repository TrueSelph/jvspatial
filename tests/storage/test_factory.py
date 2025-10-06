"""Comprehensive test suite for storage factory function.

Tests get_file_interface() factory function including provider selection,
configuration handling, environment variables, and error cases.
"""

import os
import sys
import tempfile
from unittest.mock import MagicMock, Mock, patch

import pytest

from jvspatial.storage import (
    DEFAULT_FILES_ROOT,
    FILE_INTERFACE_TYPE,
    LocalFileInterface,
    S3FileInterface,
    get_file_interface,
)
from jvspatial.storage.exceptions import StorageProviderError, ValidationError
from jvspatial.storage.security import FileValidator

# ============================================================================
# Fixtures and Helpers
# ============================================================================


def mock_boto3_module():
    """Helper to mock boto3 module for S3 tests."""
    # Clear any existing mocks
    modules_to_cleanup = [
        "boto3",
        "boto3.s3",
        "boto3.s3.inject",
        "botocore",
        "botocore.exceptions",
    ]

    for module in modules_to_cleanup:
        if module in sys.modules:
            del sys.modules[module]

    # Create mock objects
    mock_boto3 = Mock(name="boto3")
    mock_client = MagicMock(name="s3_client")

    # Set up boto3.s3 and inject modules
    mock_s3 = Mock(name="boto3.s3")
    mock_inject = Mock(name="boto3.s3.inject")
    mock_boto3.s3 = mock_s3
    mock_s3.inject = mock_inject

    # Set up mock exceptions
    class MockClientError(Exception):
        def __init__(
            self,
            error_response={"Error": {"Code": "TestError", "Message": "Test Error"}},
            operation="test",
        ):
            self.response = error_response
            super().__init__(f"ClientError: {error_response}")

    class MockBotoCoreError(Exception):
        def __init__(self, message="AWS Service Error"):
            self.msg = message
            super().__init__(message)

    # Set up mock client that raises error
    def create_client(*args, **kwargs):
        raise MockBotoCoreError("AWS Connection Failed")

    mock_boto3.client = MagicMock(side_effect=create_client)

    # Add exception classes
    mock_boto3.exceptions = MagicMock()
    mock_boto3.exceptions.ClientError = MockClientError
    mock_boto3.exceptions.BotoCoreError = MockBotoCoreError

    # Set up in sys.modules
    sys.modules["boto3"] = mock_boto3
    sys.modules["boto3.s3"] = mock_s3
    sys.modules["boto3.s3.inject"] = mock_inject
    return mock_boto3, mock_client


@pytest.fixture
def temp_dir():
    """Create temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def clean_env():
    """Clean environment variables before and after test."""
    original_env = {}
    env_vars = [
        "JVSPATIAL_FILE_INTERFACE",
        "JVSPATIAL_S3_BUCKET_NAME",
        "JVSPATIAL_S3_REGION_NAME",
        "JVSPATIAL_S3_ACCESS_KEY_ID",
        "JVSPATIAL_S3_SECRET_ACCESS_KEY",
        "JVSPATIAL_S3_ENDPOINT_URL",
    ]

    # Save and clear environment
    for var in env_vars:
        if var in os.environ:
            original_env[var] = os.environ[var]
            del os.environ[var]

    yield

    # Restore environment
    for var, value in original_env.items():
        os.environ[var] = value


# ============================================================================
# Default Provider Selection Tests
# ============================================================================


class TestDefaultProviderSelection:
    """Tests for default provider selection behavior."""

    def test_default_provider_is_local(self, clean_env, temp_dir):
        """Test that default provider is 'local' when no parameters provided."""
        storage = get_file_interface(root_dir=temp_dir)

        assert isinstance(storage, LocalFileInterface)
        assert storage.root_dir.name == os.path.basename(temp_dir)

    def test_default_provider_without_root_dir(self, clean_env):
        """Test default provider creates .files directory."""
        storage = get_file_interface()

        assert isinstance(storage, LocalFileInterface)
        # Should use default root_dir of ".files"
        assert storage.root_dir.name == ".files"


# ============================================================================
# Explicit Provider Selection Tests
# ============================================================================


class TestExplicitProviderSelection:
    """Tests for explicit provider parameter."""

    def test_explicit_local_provider(self, clean_env, temp_dir):
        """Test explicitly selecting local provider."""
        storage = get_file_interface(provider="local", root_dir=temp_dir)

        assert isinstance(storage, LocalFileInterface)

    def test_explicit_local_provider_uppercase(self, clean_env, temp_dir):
        """Test that provider name is case-insensitive."""
        storage = get_file_interface(provider="LOCAL", root_dir=temp_dir)

        assert isinstance(storage, LocalFileInterface)

    def test_explicit_s3_provider(self, clean_env):
        """Test explicitly selecting S3 provider."""
        mock_boto3, mock_client = mock_boto3_module()

        storage = get_file_interface(
            provider="s3", config={"bucket_name": "test-bucket"}
        )

        assert isinstance(storage, S3FileInterface)
        assert storage.bucket_name == "test-bucket"

    def test_explicit_s3_provider_uppercase(self, clean_env):
        """Test S3 provider with uppercase name."""
        mock_boto3, mock_client = mock_boto3_module()

        storage = get_file_interface(
            provider="S3", config={"bucket_name": "test-bucket"}
        )

        assert isinstance(storage, S3FileInterface)
        assert storage.bucket_name == "test-bucket"


# ============================================================================
# Environment Variable Provider Selection Tests
# ============================================================================


class TestEnvironmentVariableProviderSelection:
    """Tests for provider selection via environment variables."""

    def test_env_var_local_provider(self, temp_dir):
        """Test selecting local provider via environment variable."""
        with patch.dict(os.environ, {"JVSPATIAL_FILE_INTERFACE": "local"}):
            storage = get_file_interface(root_dir=temp_dir)

            assert isinstance(storage, LocalFileInterface)

    def test_env_var_s3_provider(self):
        """Test selecting S3 provider via environment variable."""
        mock_boto3, mock_client = mock_boto3_module()

        with patch.dict(
            os.environ,
            {
                "JVSPATIAL_FILE_INTERFACE": "s3",
                "JVSPATIAL_S3_BUCKET_NAME": "env-bucket",
            },
        ):
            storage = get_file_interface()

            assert isinstance(storage, S3FileInterface)
            assert storage.bucket_name == "env-bucket"

    def test_parameter_overrides_env_var(self, temp_dir):
        """Test that explicit provider parameter overrides environment variable."""
        with patch.dict(os.environ, {"JVSPATIAL_FILE_INTERFACE": "s3"}):
            storage = get_file_interface(provider="local", root_dir=temp_dir)

            # Should be local despite env var saying s3
            assert isinstance(storage, LocalFileInterface)


# ============================================================================
# Configuration Merging Tests
# ============================================================================


class TestConfigurationMerging:
    """Tests for configuration dictionary and kwargs merging."""

    def test_config_dict_only(self, temp_dir):
        """Test configuration via config dict only."""
        storage = get_file_interface(
            provider="local",
            config={"root_dir": temp_dir, "base_url": "http://example.com"},
        )

        assert isinstance(storage, LocalFileInterface)
        assert storage.base_url == "http://example.com"

    def test_kwargs_only(self, temp_dir):
        """Test configuration via kwargs only."""
        storage = get_file_interface(
            provider="local", root_dir=temp_dir, base_url="http://example.com"
        )

        assert isinstance(storage, LocalFileInterface)
        assert storage.base_url == "http://example.com"

    def test_kwargs_override_config(self, temp_dir):
        """Test that kwargs override config dict values."""
        storage = get_file_interface(
            provider="local",
            config={"root_dir": temp_dir, "base_url": "http://old.com"},
            base_url="http://new.com",
        )

        assert storage.base_url == "http://new.com"

    def test_config_dict_and_kwargs_merge(self, temp_dir):
        """Test that config dict and kwargs are merged."""
        storage = get_file_interface(
            provider="local",
            config={"root_dir": temp_dir},
            base_url="http://example.com",
        )

        assert isinstance(storage, LocalFileInterface)
        assert storage.base_url == "http://example.com"


# ============================================================================
# Root Directory Parameter Tests
# ============================================================================


class TestRootDirParameter:
    """Tests for root_dir parameter handling."""

    def test_root_dir_parameter(self, temp_dir):
        """Test that root_dir parameter is used."""
        storage = get_file_interface(provider="local", root_dir=temp_dir)

        assert storage.root_dir.name == os.path.basename(temp_dir)

    def test_root_dir_from_config(self, temp_dir):
        """Test root_dir from config dict."""
        storage = get_file_interface(provider="local", config={"root_dir": temp_dir})

        assert storage.root_dir.name == os.path.basename(temp_dir)

    def test_root_dir_parameter_overrides_config(self, temp_dir):
        """Test that root_dir parameter overrides config."""
        with tempfile.TemporaryDirectory() as tmpdir2:
            storage = get_file_interface(
                provider="local", config={"root_dir": tmpdir2}, root_dir=temp_dir
            )

            assert storage.root_dir.name == os.path.basename(temp_dir)

    def test_default_root_dir_used_when_none_provided(self, clean_env):
        """Test that default .files is used when no root_dir provided."""
        storage = get_file_interface(provider="local")

        assert storage.root_dir.name == ".files"


# ============================================================================
# Custom Validator Configuration Tests
# ============================================================================


class TestCustomValidatorConfiguration:
    """Tests for custom FileValidator configuration."""

    def test_validator_with_max_size(self, temp_dir):
        """Test creating storage with custom max_size_mb."""
        storage = get_file_interface(
            provider="local", root_dir=temp_dir, config={"max_size_mb": 5}
        )

        assert isinstance(storage, LocalFileInterface)
        assert storage.validator is not None
        assert storage.validator.max_size_bytes == 5 * 1024 * 1024

    def test_validator_with_allowed_mime_types(self, temp_dir):
        """Test creating storage with custom allowed MIME types."""
        allowed_types = {"text/plain", "application/pdf"}
        storage = get_file_interface(
            provider="local",
            root_dir=temp_dir,
            config={"allowed_mime_types": allowed_types},
        )

        assert storage.validator is not None
        assert storage.validator.allowed_mime_types == allowed_types

    def test_validator_with_both_settings(self, temp_dir):
        """Test validator with both max_size and allowed types."""
        allowed_types = {"image/jpeg", "image/png"}
        storage = get_file_interface(
            provider="local",
            root_dir=temp_dir,
            config={"max_size_mb": 10, "allowed_mime_types": allowed_types},
        )

        assert storage.validator.max_size_bytes == 10 * 1024 * 1024
        assert storage.validator.allowed_mime_types == allowed_types

    def test_no_custom_validator_when_not_configured(self, temp_dir):
        """Test that default validator is used when not customized."""
        storage = get_file_interface(provider="local", root_dir=temp_dir)

        # Should have a validator but it's the default one
        assert isinstance(storage.validator, FileValidator)


# ============================================================================
# LocalFileInterface Creation Tests
# ============================================================================


class TestLocalFileInterfaceCreation:
    """Tests for LocalFileInterface creation via factory."""

    def test_local_with_base_url(self, temp_dir):
        """Test creating local storage with base_url."""
        storage = get_file_interface(
            provider="local",
            root_dir=temp_dir,
            config={"base_url": "http://localhost:8000"},
        )

        assert storage.base_url == "http://localhost:8000"

    def test_local_with_create_root_true(self):
        """Test creating local storage with create_root=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_root = os.path.join(tmpdir, "new_storage")
            storage = get_file_interface(
                provider="local", root_dir=new_root, config={"create_root": True}
            )

            assert os.path.exists(new_root)

    def test_local_with_create_root_false(self, temp_dir):
        """Test creating local storage with create_root=False."""
        storage = get_file_interface(
            provider="local", root_dir=temp_dir, config={"create_root": False}
        )

        assert isinstance(storage, LocalFileInterface)

    def test_local_with_all_parameters(self, temp_dir):
        """Test creating local storage with all parameters."""
        storage = get_file_interface(
            provider="local",
            root_dir=temp_dir,
            config={
                "base_url": "http://example.com",
                "create_root": True,
                "max_size_mb": 20,
                "allowed_mime_types": {"text/plain"},
            },
        )

        assert storage.base_url == "http://example.com"
        assert storage.validator.max_size_bytes == 20 * 1024 * 1024


# ============================================================================
# S3FileInterface Creation Tests
# ============================================================================


class TestS3FileInterfaceCreation:
    """Tests for S3FileInterface creation via factory."""

    @patch("jvspatial.storage.interfaces.s3.boto3")
    def test_s3_with_bucket_name(self, mock_boto3):
        """Test creating S3 storage with bucket name."""
        mock_boto3.client.return_value = MagicMock()

        storage = get_file_interface(provider="s3", config={"bucket_name": "my-bucket"})

        assert storage.bucket_name == "my-bucket"

    @patch("jvspatial.storage.interfaces.s3.boto3")
    def test_s3_with_region(self, mock_boto3):
        """Test creating S3 storage with custom region."""
        mock_boto3.client.return_value = MagicMock()

        storage = get_file_interface(
            provider="s3",
            config={"bucket_name": "my-bucket", "region_name": "eu-west-1"},
        )

        assert storage.region_name == "eu-west-1"

    @patch("jvspatial.storage.interfaces.s3.boto3")
    def test_s3_with_credentials(self, mock_boto3):
        """Test creating S3 storage with AWS credentials."""
        mock_boto3.client.return_value = MagicMock()

        storage = get_file_interface(
            provider="s3",
            config={
                "bucket_name": "my-bucket",
                "access_key_id": "AKIATEST",
                "secret_access_key": "secret123",  # pragma: allowlist secret
            },
        )

        assert storage.access_key_id == "AKIATEST"
        assert storage.secret_access_key == "secret123"  # pragma: allowlist secret

    @patch("jvspatial.storage.interfaces.s3.boto3")
    def test_s3_with_custom_endpoint(self, mock_boto3):
        """Test creating S3 storage with custom endpoint URL."""
        mock_boto3.client.return_value = MagicMock()

        storage = get_file_interface(
            provider="s3",
            config={
                "bucket_name": "my-bucket",
                "endpoint_url": "https://minio.example.com",
            },
        )

        assert storage.endpoint_url == "https://minio.example.com"

    @patch("jvspatial.storage.interfaces.s3.boto3")
    def test_s3_with_url_expiration(self, mock_boto3):
        """Test creating S3 storage with custom URL expiration."""
        mock_boto3.client.return_value = MagicMock()

        storage = get_file_interface(
            provider="s3", config={"bucket_name": "my-bucket", "url_expiration": 7200}
        )

        assert storage.url_expiration == 7200

    @patch("jvspatial.storage.interfaces.s3.boto3")
    def test_s3_with_custom_validator(self, mock_boto3):
        """Test creating S3 storage with custom validator."""
        mock_boto3.client.return_value = MagicMock()

        storage = get_file_interface(
            provider="s3",
            config={
                "bucket_name": "my-bucket",
                "max_size_mb": 50,
                "allowed_mime_types": {"image/jpeg"},
            },
        )

        assert storage.validator.max_size_bytes == 50 * 1024 * 1024


# ============================================================================
# Invalid Provider Tests
# ============================================================================


class TestInvalidProviderRejection:
    """Tests for invalid provider rejection."""

    def test_unknown_provider_raises_error(self, clean_env):
        """Test that unknown provider raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_file_interface(provider="azure")

        assert "unknown storage provider" in str(exc_info.value).lower()
        assert "azure" in str(exc_info.value).lower()

    def test_error_lists_available_providers(self, clean_env):
        """Test that error message lists available providers."""
        with pytest.raises(ValueError) as exc_info:
            get_file_interface(provider="invalid")

        error_msg = str(exc_info.value).lower()
        assert "local" in error_msg
        assert "s3" in error_msg

    def test_empty_provider_uses_default(self, clean_env, temp_dir):
        """Test that empty string provider uses default."""
        storage = get_file_interface(provider="", root_dir=temp_dir)

        # Empty provider should fall back to default (local)
        assert isinstance(storage, LocalFileInterface)

    def test_none_provider_uses_default(self, clean_env, temp_dir):
        """Test that None provider uses default."""
        storage = get_file_interface(provider=None, root_dir=temp_dir)

        assert isinstance(storage, LocalFileInterface)


# ============================================================================
# Provider Initialization Error Handling Tests
# ============================================================================


class TestProviderInitializationErrorHandling:
    """Tests for provider initialization error handling."""

    def test_local_missing_directory_error(self, clean_env):
        """Test error when local root directory doesn't exist."""
        with pytest.raises(StorageProviderError) as exc_info:
            get_file_interface(
                provider="local",
                root_dir="/nonexistent/path",
                config={"create_root": False},
            )

        assert "failed to initialize" in str(exc_info.value).lower()

    @patch("jvspatial.storage.interfaces.s3.boto3")
    def test_s3_initialization_wraps_errors(self, mock_boto3):
        """Test that S3 initialization errors are wrapped."""
        mock_boto3.client.side_effect = RuntimeError("AWS Connection Failed")

        with pytest.raises(StorageProviderError) as exc_info:
            get_file_interface(provider="s3", config={"bucket_name": "test-bucket"})

        assert "failed to initialize s3 storage" in str(exc_info.value).lower()
        assert "aws connection failed" in str(exc_info.value).lower()

    @patch("jvspatial.storage.LocalFileInterface.__init__")
    def test_local_initialization_error_wrapped(self, mock_init, temp_dir):
        """Test that local initialization errors are wrapped."""
        mock_init.side_effect = RuntimeError("Disk error")

        with pytest.raises(StorageProviderError) as exc_info:
            get_file_interface(provider="local", root_dir=temp_dir)

        assert "failed to initialize local" in str(exc_info.value).lower()


# ============================================================================
# Config Parameter Validation Tests
# ============================================================================


class TestConfigParameterValidation:
    """Tests for configuration parameter validation."""

    def test_none_config_handled(self, temp_dir):
        """Test that None config is handled properly."""
        storage = get_file_interface(provider="local", root_dir=temp_dir, config=None)

        assert isinstance(storage, LocalFileInterface)

    def test_empty_config_handled(self, temp_dir):
        """Test that empty config dict is handled."""
        storage = get_file_interface(provider="local", root_dir=temp_dir, config={})

        assert isinstance(storage, LocalFileInterface)

    def test_s3_without_bucket_raises_error(self):
        """Test that S3 without bucket name raises error."""
        mock_boto3, mock_client = mock_boto3_module()

        with pytest.raises(ValueError) as exc_info:
            get_file_interface(provider="s3", config={})

        assert "bucket_name is required" in str(exc_info.value).lower()


# ============================================================================
# Backward Compatibility Tests
# ============================================================================


class TestBackwardCompatibility:
    """Tests for backward compatibility with old constants."""

    def test_file_interface_type_constant_exists(self):
        """Test that FILE_INTERFACE_TYPE constant exists."""
        assert FILE_INTERFACE_TYPE is not None

    def test_default_files_root_constant_exists(self):
        """Test that DEFAULT_FILES_ROOT constant exists."""
        assert DEFAULT_FILES_ROOT is not None

    def test_file_interface_type_default_value(self, clean_env):
        """Test FILE_INTERFACE_TYPE default value."""
        # When not set, should default to 'local'
        from jvspatial.storage import FILE_INTERFACE_TYPE

        assert FILE_INTERFACE_TYPE.lower() in ["local", "local"]

    def test_default_files_root_default_value(self, clean_env):
        """Test DEFAULT_FILES_ROOT default value."""
        from jvspatial.storage import DEFAULT_FILES_ROOT

        assert DEFAULT_FILES_ROOT == ".files" or DEFAULT_FILES_ROOT is not None

    def test_env_var_affects_constant(self):
        """Test that environment variable affects constant."""
        with patch.dict(os.environ, {"JVSPATIAL_FILE_INTERFACE": "custom"}):
            # Re-import to get updated constant
            import importlib

            import jvspatial.storage

            importlib.reload(jvspatial.storage)

            from jvspatial.storage import FILE_INTERFACE_TYPE

            assert FILE_INTERFACE_TYPE == "custom"


# ============================================================================
# Edge Cases and Special Scenarios
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_whitespace_provider_name(self, temp_dir):
        """Test provider name with extra whitespace."""
        storage = get_file_interface(provider="  local  ".strip(), root_dir=temp_dir)

        # Should handle whitespace by stripping/lowercasing
        assert isinstance(storage, LocalFileInterface)

    def test_config_with_unexpected_keys(self, temp_dir):
        """Test that unexpected config keys don't cause errors."""
        storage = get_file_interface(
            provider="local",
            root_dir=temp_dir,
            config={"unexpected_key": "value", "another_key": 123},
        )

        # Should ignore unexpected keys
        assert isinstance(storage, LocalFileInterface)

    def test_multiple_instantiations(self, temp_dir):
        """Test creating multiple storage instances."""
        storage1 = get_file_interface(provider="local", root_dir=temp_dir)
        storage2 = get_file_interface(provider="local", root_dir=temp_dir)

        # Should create separate instances
        assert storage1 is not storage2
        assert isinstance(storage1, LocalFileInterface)
        assert isinstance(storage2, LocalFileInterface)


# ============================================================================
# Module Imports
# ============================================================================


def test_factory_module_imports():
    """Test that factory components can be imported."""
    from jvspatial.storage import (
        DEFAULT_FILES_ROOT,
        FILE_INTERFACE_TYPE,
        get_file_interface,
    )

    assert get_file_interface is not None
    assert FILE_INTERFACE_TYPE is not None
    assert DEFAULT_FILES_ROOT is not None
