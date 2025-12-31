"""Lambda Server extension for AWS Lambda deployments.

This module provides LambdaServer, a specialized server class for AWS Lambda
deployments that extends Server with Lambda-specific functionality.
"""

import os
from typing import Any, Dict, Optional, Union

from jvspatial.api.config import ServerConfig
from jvspatial.api.server import Server


class LambdaServer(Server):
    """Specialized server class for AWS Lambda/serverless deployments.

    This class extends Server with Lambda-specific functionality including:
    - Lambda environment detection and configuration
    - Lambda temp directory management
    - Mangum handler creation
    - Serverless-specific database and file storage configuration

    LambdaServer constrains the server interface to what's applicable for
    Lambda deployments. Methods like `run()` are not available as Lambda
    handles server execution.

    Example:
        ```python
        from jvspatial.api.lambda_server import LambdaServer

        # Create Lambda server (DynamoDB is default)
        server = LambdaServer(
            title="My Lambda API",
            dynamodb_table_name="my-table"
        )

        # Get Lambda handler
        handler = server.get_lambda_handler()
        ```

    Note:
        LambdaServer automatically configures:
        - Database paths to use /tmp for file-based databases
        - File storage to use /tmp for local storage
        - Mangum handler for AWS Lambda compatibility (created lazily on first access)

    Important:
        The Lambda handler is created lazily when get_lambda_handler() is called,
        not during initialization. This ensures all endpoints decorated with @endpoint
        are registered before the FastAPI app is created.
    """

    def __init__(
        self: "LambdaServer",
        config: Optional[Union[ServerConfig, Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the LambdaServer.

        Args:
            config: Server configuration as ServerConfig or dict
            **kwargs: Additional configuration parameters

        Note:
            LambdaServer always runs in serverless mode. DynamoDB is the default database.
        """
        # Set DynamoDB as default database if not specified
        if isinstance(config, dict):
            if "db_type" not in config:
                config["db_type"] = "dynamodb"
        elif config is None:
            config = {"db_type": "dynamodb"}
        else:
            # ServerConfig instance - update via kwargs
            pass

        if "db_type" not in kwargs and "db_type" not in (config or {}):
            kwargs["db_type"] = "dynamodb"

        # Lambda-specific attributes
        self._lambda_handler: Optional[Any] = None

        # Extract Lambda-specific configuration (not part of ServerConfig)
        self._serverless_lifespan: str = kwargs.pop("serverless_lifespan", "auto")
        self._serverless_api_gateway_base_path: Optional[str] = kwargs.pop(
            "serverless_api_gateway_base_path", None
        )
        self._lambda_temp_dir: Optional[str] = kwargs.pop("lambda_temp_dir", None)

        # Merge config with Lambda-specific adjustments
        merged_config = self._merge_config(config, kwargs)

        # Apply Lambda-specific configuration adjustments
        merged_config = self._apply_lambda_config(merged_config)

        # Call parent __init__ with adjusted config
        super().__init__(config=merged_config, **{})

    def _apply_lambda_config(
        self: "LambdaServer", config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply Lambda-specific configuration adjustments.

        Args:
            config: Configuration dictionary

        Returns:
            Adjusted configuration dictionary
        """
        # Get lambda temp directory
        lambda_temp = (
            self._lambda_temp_dir
            or config.get("lambda_temp_dir")
            or os.getenv("JVSPATIAL_LAMBDA_TEMP_DIR")
            or self._get_lambda_temp_dir()
        )

        if lambda_temp and self._is_lambda_environment():
            # Store lambda temp directory
            if not self._lambda_temp_dir:
                self._lambda_temp_dir = lambda_temp

            # Force environment variables to use /tmp for file-based databases
            db_type = config.get("db_type", "json")
            os.environ["JVSPATIAL_DB_TYPE"] = db_type

            if db_type == "json":
                os.environ["JVSPATIAL_JSONDB_PATH"] = f"{lambda_temp}/jvdb"
            elif db_type == "sqlite":
                os.environ["JVSPATIAL_SQLITE_PATH"] = (
                    f"{lambda_temp}/jvdb/sqlite/jvspatial.db"
                )

            # Handle S3 configuration for file-based databases
            s3_bucket = config.get("s3_bucket_name") or os.getenv(
                "JVSPATIAL_S3_BUCKET_NAME"
            )

            if ("db_path" not in config or not config.get("db_path")) and db_type in [
                "json",
                "sqlite",
            ]:
                if s3_bucket:
                    # Automatically switch to DynamoDB for persistent storage
                    config["db_type"] = "dynamodb"
                    if "dynamodb_table_name" not in config or not config.get(
                        "dynamodb_table_name"
                    ):
                        table_name = s3_bucket.replace("/", "-").replace("_", "-")
                        config["dynamodb_table_name"] = f"{table_name}-jvspatial"
                    s3_region = config.get("s3_region") or os.getenv(
                        "JVSPATIAL_S3_REGION"
                    )
                    if s3_region and (
                        "dynamodb_region" not in config
                        or not config.get("dynamodb_region")
                    ):
                        config["dynamodb_region"] = s3_region
                    config["_s3_db_path_log"] = (
                        f"🔄 Automatically switching from {db_type} to DynamoDB for serverless mode. "
                        f"Using S3 bucket '{s3_bucket}' to derive DynamoDB table name."
                    )
                else:
                    # Fallback to Lambda temp (ephemeral) with warning
                    if lambda_temp:
                        if db_type == "json":
                            config["db_path"] = f"{lambda_temp}/jvdb"
                            os.environ["JVSPATIAL_JSONDB_PATH"] = f"{lambda_temp}/jvdb"
                        else:  # sqlite
                            config["db_path"] = (
                                f"{lambda_temp}/jvdb/sqlite/jvspatial.db"
                            )
                            os.environ["JVSPATIAL_SQLITE_PATH"] = (
                                f"{lambda_temp}/jvdb/sqlite/jvspatial.db"
                            )
                    config["_s3_db_path_warning"] = (
                        f"⚠️  S3 bucket not configured for {db_type} database in serverless mode. "
                        "File-based databases are ephemeral in Lambda (/tmp). "
                        "Consider using DynamoDB (db_type='dynamodb') or configure S3 bucket for automatic DynamoDB setup."
                    )

            # Automatically set file storage root to Lambda temp if using local storage
            if (
                config.get("file_storage_provider") == "local"
                and (
                    "file_storage_root" not in config
                    or config.get("file_storage_root") == ".files"
                )
                and lambda_temp
            ):
                config["file_storage_root"] = f"{lambda_temp}/.files"
                config["_file_storage_warning"] = (
                    "⚠️  Using local file storage in serverless mode. "
                    "Consider using S3 file storage provider for persistence."
                )

        return config

    def _initialize_serverless_handler(self: "LambdaServer") -> None:
        """Initialize serverless Lambda handler."""
        try:
            from mangum import Mangum
        except ImportError:
            self._logger.warning(
                "Mangum is required for serverless deployment but not installed. "
                "Install it with: pip install mangum>=0.17.0 "
                "or pip install jvspatial[serverless]"
            )
            return

        # Lambda temp directory should already be set in __init__, but ensure it's set
        if self._is_lambda_environment() and not self._lambda_temp_dir:
            lambda_temp = self._get_lambda_temp_dir()
            if lambda_temp:
                self._lambda_temp_dir = lambda_temp
                self._logger.info(f"📁 Lambda temp directory detected: {lambda_temp}")

        app = self.get_app()
        mangum_config: Dict[str, Any] = {
            "lifespan": self._serverless_lifespan,
        }
        if self._serverless_api_gateway_base_path:
            mangum_config["api_gateway_base_path"] = (
                self._serverless_api_gateway_base_path
            )
        self._lambda_handler = Mangum(app, **mangum_config)

        self._logger.info(
            "🚀 Serverless Lambda handler initialized. Use server.get_lambda_handler() to get the handler."
        )

    @staticmethod
    def _is_lambda_environment() -> bool:
        """Check if running in AWS Lambda environment."""
        return (
            os.getenv("LAMBDA_TASK_ROOT") is not None
            or os.getenv("AWS_EXECUTION_ENV") is not None
        )

    @staticmethod
    def _get_lambda_temp_dir() -> Optional[str]:
        """Get the Lambda temp directory path."""
        if LambdaServer._is_lambda_environment():
            temp_dir = "/tmp"
            if os.path.exists(temp_dir) and os.access(temp_dir, os.W_OK):
                return temp_dir
        return None

    @property
    def lambda_handler(self: "LambdaServer") -> Optional[Any]:
        """Get the Lambda handler.

        Returns:
            Lambda handler function
        """
        return self._lambda_handler

    def get_lambda_temp_dir(self: "LambdaServer") -> Optional[str]:
        """Get the Lambda temp directory path.

        Returns:
            Lambda temp directory path (/tmp) if in Lambda, None otherwise
        """
        if self._lambda_temp_dir:
            return self._lambda_temp_dir

        if self._is_lambda_environment():
            return self._get_lambda_temp_dir()

        return None

    def get_lambda_handler(
        self: "LambdaServer",
        **mangum_kwargs: Any,
    ) -> Any:
        """Get the Lambda handler.

        The handler is created lazily when this method is first called, ensuring
        all endpoints are registered before the FastAPI app is created.
        This method returns the handler, which should be assigned to a module-level
        variable for AWS Lambda to access.

        Args:
            **mangum_kwargs: Additional Mangum configuration (ignored if handler already exists)

        Returns:
            Lambda handler function compatible with AWS Lambda

        Example:
            ```python
            from jvspatial.api.lambda_server import LambdaServer

            server = LambdaServer(title="My Lambda API")

            # Get handler and assign to module-level variable
            handler = server.get_lambda_handler()

            # Lambda will call this handler (e.g., "lambda_function.handler")
            ```
        """
        if mangum_kwargs and self._lambda_handler is not None:
            self._logger.warning(
                "Lambda handler already initialized. Additional mangum_kwargs are ignored."
            )

        if self._lambda_handler is None:
            # Create handler on-demand
            try:
                from mangum import Mangum
            except ImportError:
                raise ImportError(
                    "Mangum is required for serverless deployment. "
                    "Install it with: pip install mangum>=0.17.0 "
                    "or pip install jvspatial[serverless]"
                ) from None

            app = self.get_app()
            mangum_config = {
                "lifespan": self._serverless_lifespan,
                **mangum_kwargs,
            }
            if self._serverless_api_gateway_base_path:
                mangum_config["api_gateway_base_path"] = (
                    self._serverless_api_gateway_base_path
                )
            self._lambda_handler = Mangum(app, **mangum_config)

        return self._lambda_handler

    # Override run() to prevent usage in Lambda
    def run(
        self: "LambdaServer",
        host: Optional[str] = None,
        port: Optional[int] = None,
        reload: Optional[bool] = None,
        **uvicorn_kwargs: Any,
    ) -> None:
        """Run is not available for LambdaServer.

        Lambda handles server execution. Use get_lambda_handler() to get the handler.
        """
        raise RuntimeError(
            "LambdaServer does not support run(). "
            "Lambda handles server execution. Use get_lambda_handler() to get the handler for AWS Lambda."
        )
