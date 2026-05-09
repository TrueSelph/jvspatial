"""AWS S3 storage implementation.

This module provides an S3-based implementation of the FileStorageInterface
with lazy boto3 import, streaming support, and pre-signed URLs.
"""

import asyncio
import hashlib
import logging
from asyncio import to_thread
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional, cast

from jvspatial.env import env
from jvspatial.utils.retry import retry_async

from ..exceptions import (
    AccessDeniedError,
    FileNotFoundError,
    FileSizeLimitError,
    PathTraversalError,
    StorageProviderError,
)
from ..security.path_sanitizer import PathSanitizer
from ..security.validator import FileValidator
from .base import FileStorageInterface

# Lazy import boto3 (optional dependency)
try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    HAS_BOTO3 = True
except ImportError:
    boto3 = None
    ClientError = None
    BotoCoreError = None
    HAS_BOTO3 = False

# FastAPI imports (optional - only for serve_file)
try:

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


logger = logging.getLogger(__name__)


# S3 error codes worth retrying with backoff. The application would
# otherwise see a single SlowDown / 503 / brief outage as a hard
# failure even though boto3's transfer manager is already resilient
# for chunked uploads. These wrap the *control* plane (head/get/delete/
# put_object) where transient errors aren't auto-retried.
_S3_THROTTLE_CODES = frozenset(
    {
        "SlowDown",
        "RequestTimeout",
        "ServiceUnavailable",
        "InternalError",
        "503",
        "500",
    }
)


def _is_s3_throttle_error(exc: BaseException) -> bool:
    """Predicate for the shared retry helper on S3 ops."""
    if ClientError is None or not isinstance(exc, ClientError):
        return False
    err = getattr(exc, "response", {}).get("Error", {}) or {}
    code = err.get("Code")
    if code in _S3_THROTTLE_CODES:
        return True
    # boto3 sometimes surfaces transient errors via HTTP status only.
    meta = getattr(exc, "response", {}).get("ResponseMetadata", {}) or {}
    status = meta.get("HTTPStatusCode")
    return status in (500, 502, 503, 504)


# Direct serve extensions (small text files that can be sent directly)
DIRECT_SERVE_EXTENSIONS = {
    ".pdf",
    ".html",
    ".txt",
    ".js",
    ".css",
    ".json",
    ".xml",
    ".svg",
    ".csv",
    ".ico",
}


class S3FileInterface(FileStorageInterface):
    """AWS S3 storage implementation.

    This provider stores files on AWS S3 with comprehensive security checks,
    streaming support, and pre-signed URLs. Boto3 is imported lazily to avoid
    requiring it as a dependency when not using S3.

    Features:
        - Async I/O using asyncio.to_thread()
        - Lazy boto3 import (only when S3 is used)
        - Path sanitization and validation
        - Streaming support for large files
        - Pre-signed URLs with expiration
        - Direct serve for small text files
        - Thread-safe operations

    Configuration via live environment variables:
        - JVSPATIAL_S3_BUCKET_NAME: S3 bucket name
        - JVSPATIAL_S3_REGION: AWS region (default: us-east-1)
        - JVSPATIAL_S3_ACCESS_KEY: AWS access key ID
        - JVSPATIAL_S3_SECRET_KEY: AWS secret access key
        - JVSPATIAL_S3_ENDPOINT_URL: Custom endpoint URL (for S3-compatible services)

    Args:
        bucket_name: S3 bucket name
        region_name: AWS region (default: us-east-1)
        access_key_id: AWS access key ID (optional, uses env/credentials)
        secret_access_key: AWS secret access key (optional)
        endpoint_url: Custom endpoint URL (optional, for S3-compatible services)
        validator: Optional FileValidator instance
        url_expiration: Default URL expiration in seconds (default: 3600)

    Example:
        >>> storage = S3FileInterface(
        ...     bucket_name="my-bucket",
        ...     region_name="us-west-2"
        ... )
        >>> await storage.save_file("uploads/doc.pdf", file_bytes)
    """

    # 8 MiB default multipart threshold. Anything bigger goes through
    # boto3's TransferManager which splits, parallelizes, and resumes
    # automatically. Override with ``multipart_threshold`` in the
    # constructor or the ``JVSPATIAL_S3_MULTIPART_THRESHOLD`` env var.
    DEFAULT_MULTIPART_THRESHOLD = 8 * 1024 * 1024

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region_name: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        validator: Optional[FileValidator] = None,
        url_expiration: int = 3600,
        multipart_threshold: Optional[int] = None,
    ):
        """Initialize S3 storage.

        Args:
            bucket_name: S3 bucket name
            region_name: AWS region
            access_key_id: AWS access key ID
            secret_access_key: AWS secret access key
            endpoint_url: Custom endpoint URL
            validator: Optional FileValidator instance
            url_expiration: Default URL expiration in seconds
            multipart_threshold: Files at or above this size (in bytes)
                are uploaded via boto3's automatic multipart transfer
                manager. Default 8 MiB. Also configurable via the
                ``JVSPATIAL_S3_MULTIPART_THRESHOLD`` env var.
        """
        # Check if boto3 is available
        if not HAS_BOTO3:
            raise ImportError(
                "boto3 is required for S3 storage. "
                "Install it with: pip install boto3"
            )

        self._boto3 = boto3
        self._ClientError = ClientError
        self._BotoCoreError = BotoCoreError

        self.bucket_name = bucket_name or env("JVSPATIAL_S3_BUCKET_NAME")
        self.region_name = region_name or env(
            "JVSPATIAL_S3_REGION", default="us-east-1"
        )
        self.access_key_id = access_key_id or env("JVSPATIAL_S3_ACCESS_KEY")
        self.secret_access_key = secret_access_key or env("JVSPATIAL_S3_SECRET_KEY")
        self.endpoint_url = endpoint_url or env("JVSPATIAL_S3_ENDPOINT_URL")

        if not self.bucket_name:
            raise ValueError(
                "bucket_name is required. Provide it as argument or set "
                "JVSPATIAL_S3_BUCKET_NAME environment variable"
            )

        self.validator = validator or FileValidator()
        self.url_expiration = url_expiration

        # Resolve multipart threshold: explicit arg -> env -> class default.
        if multipart_threshold is not None:
            self.multipart_threshold = int(multipart_threshold)
        else:
            env_threshold = env("JVSPATIAL_S3_MULTIPART_THRESHOLD", parse=int)
            self.multipart_threshold = (
                int(env_threshold)
                if env_threshold
                else self.DEFAULT_MULTIPART_THRESHOLD
            )

        # Initialize S3 client
        self._init_client()

        logger.info(
            f"S3 storage initialized: bucket={self.bucket_name}, "
            f"region={self.region_name}"
        )

    def _init_client(self):
        """Initialize boto3 S3 client."""
        client_kwargs = {"service_name": "s3", "region_name": self.region_name}

        # Add credentials if provided
        if self.access_key_id and self.secret_access_key:
            client_kwargs["aws_access_key_id"] = self.access_key_id
            client_kwargs["aws_secret_access_key"] = self.secret_access_key

        # Add custom endpoint if provided
        if self.endpoint_url:
            client_kwargs["endpoint_url"] = self.endpoint_url

        self.s3_client = self._boto3.client(**client_kwargs)
        logger.debug("S3 client initialized")

    async def _run_with_throttle_retry(
        self, op_name: str, coro_factory: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Wrap an S3 op with throttle-error retry.

        SlowDown / 5xx / RequestTimeout get exponential backoff with
        full jitter; non-throttle ``ClientError``s propagate
        immediately and are handled by the caller's normal error
        mapping.
        """
        return await retry_async(
            coro_factory,
            retry_on=_is_s3_throttle_error,
            max_attempts=4,
            base_delay=0.2,
            max_delay=4.0,
            jitter=True,
        )

    def _sanitize_key(self, file_path: str) -> str:
        """Sanitize S3 object key.

        Args:
            file_path: Relative file path

        Returns:
            Sanitized S3 key

        Raises:
            PathTraversalError: If path is unsafe
        """
        # Sanitize path (no base_dir for S3 - bucket is the root)
        sanitized = PathSanitizer.sanitize_path(file_path)

        # S3 keys should not start with /
        sanitized = sanitized.lstrip("/")

        return sanitized

    def _handle_s3_error(self, error: Exception, operation: str) -> Exception:
        """Convert S3 errors to storage exceptions.

        Args:
            error: Original exception
            operation: Operation that failed

        Returns:
            Appropriate storage exception
        """
        if isinstance(error, self._ClientError):
            error_code = error.response.get("Error", {}).get("Code", "Unknown")
            error_msg = error.response.get("Error", {}).get("Message", str(error))

            if error_code == "NoSuchKey":
                return FileNotFoundError(
                    f"File not found in S3: {error_msg}", file_path=None
                )
            elif error_code in ("AccessDenied", "Forbidden"):
                return AccessDeniedError(f"Access denied: {error_msg}", file_path=None)
            else:
                return StorageProviderError(
                    f"S3 error ({error_code}): {error_msg}",
                    provider="s3",
                    operation=operation,
                )

        return StorageProviderError(
            f"S3 operation failed: {error}", provider="s3", operation=operation
        )

    async def save_file(
        self, file_path: str, content: bytes, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Upload file to S3.

        Args:
            file_path: Relative file path (becomes S3 key)
            content: File content as bytes
            metadata: Optional metadata (stored as S3 object metadata)

        Returns:
            Dict with file information

        Raises:
            ValidationError: If file fails validation
            StorageProviderError: If upload fails
        """
        logger.info(f"Uploading to S3: {file_path} ({len(content)} bytes)")

        try:
            from pathlib import Path

            from ..internal_markers import (
                should_skip_mime_allowlist,
                trivial_marker_validation,
            )

            filename = Path(file_path).name
            if should_skip_mime_allowlist(file_path, metadata):
                file_size = len(content)
                if file_size > self.validator.max_size_bytes:
                    max_mb = self.validator.max_size_bytes / (1024 * 1024)
                    actual_mb = file_size / (1024 * 1024)
                    raise FileSizeLimitError(
                        f"File size ({actual_mb:.2f}MB) exceeds limit ({max_mb:.2f}MB)",
                        file_size=file_size,
                        max_size=self.validator.max_size_bytes,
                    )
                validation = trivial_marker_validation(file_path, content)
                logger.debug(
                    "Skipping MIME allowlist for internal marker: %s", file_path
                )
            else:
                validation = self.validator.validate_file(
                    content=content, filename=filename
                )
                logger.debug(f"File validation passed: {validation}")

            # Sanitize S3 key
            s3_key = self._sanitize_key(file_path)

            # Detect content type
            content_type = validation.get("mime_type", "application/octet-stream")

            # Build the metadata header dict once -- both code paths use it.
            extra_metadata: Optional[Dict[str, str]] = None
            if metadata:
                extra_metadata = {
                    k.lower().replace("-", "_"): str(v) for k, v in metadata.items()
                }

            content_size = len(content)
            if content_size >= self.multipart_threshold:
                # Multipart path: boto3's TransferManager handles
                # splitting, parallel part upload, and resumption. We
                # feed it a BytesIO wrapper around the in-memory bytes.
                import io

                from boto3.s3.transfer import TransferConfig

                transfer_config = TransferConfig(
                    multipart_threshold=self.multipart_threshold,
                    multipart_chunksize=max(
                        self.multipart_threshold // 2,
                        5 * 1024 * 1024,  # S3 minimum part size
                    ),
                    use_threads=True,
                )
                extra_args: Dict[str, Any] = {"ContentType": content_type}
                if extra_metadata:
                    extra_args["Metadata"] = extra_metadata

                logger.info(
                    "S3 upload via multipart: %s (%d bytes, threshold=%d)",
                    s3_key,
                    content_size,
                    self.multipart_threshold,
                )

                async def _multipart_upload() -> None:
                    await asyncio.to_thread(
                        self.s3_client.upload_fileobj,
                        io.BytesIO(content),
                        self.bucket_name,
                        s3_key,
                        ExtraArgs=extra_args,
                        Config=transfer_config,
                    )

                await self._run_with_throttle_retry(
                    "save_file (multipart)", _multipart_upload
                )
            else:
                # Small-object path: single put_object call.
                put_kwargs: Dict[str, Any] = {
                    "Bucket": self.bucket_name,
                    "Key": s3_key,
                    "Body": content,
                    "ContentType": content_type,
                }
                if extra_metadata:
                    put_kwargs["Metadata"] = extra_metadata

                async def _put_object() -> None:
                    await asyncio.to_thread(self.s3_client.put_object, **put_kwargs)

                await self._run_with_throttle_retry("save_file", _put_object)

            logger.info(f"File uploaded to S3: {s3_key}")

            # Calculate checksum
            checksum = hashlib.md5(content).hexdigest()

            # Build result
            result = {
                "path": file_path,
                "size": len(content),
                "checksum": checksum,
                "storage_url": f"s3://{self.bucket_name}/{s3_key}",
                "metadata": metadata or {},
            }

            return result

        except Exception as e:
            if isinstance(e, (PathTraversalError, AccessDeniedError)):
                raise

            logger.error(f"Failed to upload file to S3: {e}")
            raise self._handle_s3_error(e, "save")

    async def get_file(self, file_path: str) -> Optional[bytes]:
        """Download file from S3.

        Args:
            file_path: Relative file path (S3 key)

        Returns:
            File content as bytes, or None if not found

        Raises:
            StorageProviderError: If download fails
        """
        logger.debug(f"Downloading from S3: {file_path}")

        try:
            s3_key = self._sanitize_key(file_path)

            async def _get_object_op() -> Any:
                return await to_thread(
                    self.s3_client.get_object,
                    Bucket=self.bucket_name,
                    Key=s3_key,
                )

            # Download from S3 with throttle retry.
            response = await self._run_with_throttle_retry("get_file", _get_object_op)

            # Read content
            content = cast(bytes, await to_thread(response["Body"].read))
            logger.debug(f"Downloaded from S3: {s3_key} ({len(content)} bytes)")

            return content

        except self._ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                logger.warning(f"File not found in S3: {file_path}")
                return None
            raise self._handle_s3_error(e, "get")
        except Exception as e:
            if isinstance(e, PathTraversalError):
                raise
            logger.error(f"Failed to download from S3: {e}")
            raise self._handle_s3_error(e, "get")

    async def stream_file(  # type: ignore[override,misc]
        self, file_path: str, chunk_size: int = 8192
    ) -> AsyncIterator[bytes]:
        """Stream file from S3 in chunks.

        Args:
            file_path: Relative file path (S3 key)
            chunk_size: Size of chunks to yield (default: 8KB)

        Returns:
            AsyncIterator of file content in chunks

        Raises:
            FileNotFoundError: If file doesn't exist
            StorageProviderError: If streaming fails
        """

        logger.debug(f"Streaming from S3: {file_path} (chunk_size={chunk_size})")

        try:
            s3_key = self._sanitize_key(file_path)

            # Get object from S3
            response = await asyncio.to_thread(
                self.s3_client.get_object, Bucket=self.bucket_name, Key=s3_key
            )

            # Stream content in chunks
            body = response["Body"]

            def _read_chunks():
                """Synchronous chunk reader."""
                while True:
                    chunk = body.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
                body.close()

            # Yield chunks asynchronously
            for chunk in await asyncio.to_thread(list, _read_chunks()):
                yield chunk

            logger.debug(f"S3 streaming completed: {s3_key}")

        except self._ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                raise FileNotFoundError(
                    f"File not found in S3: {file_path}", file_path=file_path
                )
            raise self._handle_s3_error(e, "stream")
        except Exception as e:
            if isinstance(e, (PathTraversalError, FileNotFoundError)):
                raise
            logger.error(f"Failed to stream from S3: {e}")
            raise self._handle_s3_error(e, "stream")

    async def delete_file(self, file_path: str) -> bool:
        """Delete file from S3.

        Args:
            file_path: Relative file path (S3 key)

        Returns:
            True if file was deleted, False if didn't exist

        Raises:
            StorageProviderError: If delete fails
        """
        logger.info(f"Deleting from S3: {file_path}")

        try:
            s3_key = self._sanitize_key(file_path)

            # Check if object exists first
            try:
                await to_thread(
                    self.s3_client.head_object, Bucket=self.bucket_name, Key=s3_key
                )
            except self._ClientError as e:
                if e.response.get("Error", {}).get("Code") == "404":
                    logger.warning(f"File not found in S3: {file_path}")
                    return False
                raise

            # Delete object with throttle retry.
            async def _delete_op() -> None:
                await asyncio.to_thread(
                    self.s3_client.delete_object,
                    Bucket=self.bucket_name,
                    Key=s3_key,
                )

            await self._run_with_throttle_retry("delete_file", _delete_op)

            logger.info(f"File deleted from S3: {s3_key}")
            return True

        except Exception as e:
            if isinstance(e, PathTraversalError):
                raise
            logger.error(f"Failed to delete from S3: {e}")
            raise self._handle_s3_error(e, "delete")

    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists in S3.

        Args:
            file_path: Relative file path (S3 key)

        Returns:
            True if file exists, False otherwise
        """
        try:
            s3_key = self._sanitize_key(file_path)

            await asyncio.to_thread(
                self.s3_client.head_object, Bucket=self.bucket_name, Key=s3_key
            )
            return True

        except self._ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                return False
            logger.error(f"Error checking S3 file existence: {e}")
            return False
        except Exception:
            return False

    async def get_metadata(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get S3 object metadata.

        Args:
            file_path: Relative file path (S3 key)

        Returns:
            Dict with file metadata or None if not found
        """
        logger.debug(f"Getting S3 metadata for: {file_path}")

        try:
            s3_key = self._sanitize_key(file_path)

            # Get object metadata
            response = await asyncio.to_thread(
                self.s3_client.head_object, Bucket=self.bucket_name, Key=s3_key
            )

            # Build metadata
            metadata = {
                "size": response.get("ContentLength", 0),
                "content_type": response.get("ContentType", "application/octet-stream"),
                "modified_at": (
                    response.get("LastModified", "").isoformat()
                    if response.get("LastModified")
                    else None
                ),
            }

            # Add ETag as checksum
            if "ETag" in response:
                metadata["checksum"] = response["ETag"].strip('"')

            # Add custom metadata
            if "Metadata" in response:
                metadata["custom_metadata"] = response["Metadata"]

            logger.debug(f"S3 metadata retrieved: {file_path}")
            return metadata

        except self._ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
                logger.warning(f"File not found in S3: {file_path}")
                return None
            logger.error(f"Failed to get S3 metadata: {e}")
            return None
        except Exception as e:
            if not isinstance(e, PathTraversalError):
                logger.error(f"Failed to get S3 metadata: {e}")
            return None

    async def get_file_url(
        self, file_path: str, expires_in: int = 3600
    ) -> Optional[str]:
        """Generate pre-signed URL for S3 object.

        Args:
            file_path: Relative file path (S3 key)
            expires_in: URL expiration in seconds (default: 3600)

        Returns:
            Pre-signed URL or None if error
        """
        logger.debug(f"Generating pre-signed URL for: {file_path}")

        try:
            s3_key = self._sanitize_key(file_path)

            # Check if file exists
            if not await self.file_exists(file_path):
                logger.warning(
                    f"Cannot generate URL for non-existent file: {file_path}"
                )
                return None

            # Generate pre-signed URL
            url = cast(
                str,
                await asyncio.to_thread(
                    self.s3_client.generate_presigned_url,
                    "get_object",
                    Params={"Bucket": self.bucket_name, "Key": s3_key},
                    ExpiresIn=expires_in,
                ),
            )

            logger.debug(f"Pre-signed URL generated (expires in {expires_in}s)")
            return url

        except Exception as e:
            if not isinstance(e, PathTraversalError):
                logger.error(f"Failed to generate pre-signed URL: {e}")
            return None

    async def serve_file(self, file_path: str) -> AsyncIterator[bytes]:  # type: ignore[override,misc]
        """Serve file from S3.

        For S3, this determines whether to serve directly (small text files)
        or stream (large binary files) based on file extension.

        Args:
            file_path: Relative file path (S3 key)

        Yields:
            File content chunks

        Raises:
            FileNotFoundError: If file doesn't exist
        """

        logger.debug(f"Serving file from S3: {file_path}")

        # Check if file exists
        if not await self.file_exists(file_path):
            raise FileNotFoundError(
                f"File not found in S3: {file_path}", file_path=file_path
            )

        # Determine serving strategy based on extension
        from pathlib import Path

        extension = Path(file_path).suffix.lower()

        if extension in DIRECT_SERVE_EXTENSIONS:
            # Direct serve for small text files
            logger.debug(f"Direct serving {extension} file")
            content = await self.get_file(file_path)
            if content:
                yield content
        else:
            # Stream for other files (likely large or binary)
            logger.debug(f"Streaming {extension} file")
            async for chunk in self.stream_file(file_path):
                yield chunk

    async def list_files(
        self, prefix: str = "", max_results: int = 1000
    ) -> List[Dict[str, Any]]:
        """List files in S3 bucket.

        Args:
            prefix: S3 key prefix to filter results
            max_results: Maximum number of results

        Returns:
            List of file info dicts
        """
        logger.debug(f"Listing S3 files with prefix: {prefix}")

        try:
            # Sanitize prefix
            s3_prefix = self._sanitize_key(prefix) if prefix else ""

            # List objects
            response = await asyncio.to_thread(
                self.s3_client.list_objects_v2,
                Bucket=self.bucket_name,
                Prefix=s3_prefix,
                MaxKeys=max_results,
            )

            # Build results
            results = []
            for obj in response.get("Contents", []):
                results.append(
                    {
                        "path": obj["Key"],
                        "size": obj["Size"],
                        "modified_at": obj["LastModified"].isoformat(),
                        "checksum": obj.get("ETag", "").strip('"'),
                    }
                )

            logger.debug(f"Listed {len(results)} S3 objects")
            return results

        except Exception as e:
            logger.error(f"Failed to list S3 files: {e}")
            return []

    async def get_storage_info(self) -> Dict[str, Any]:
        """Get S3 storage information.

        Returns:
            Dict with storage information
        """
        return {
            "provider": "S3FileInterface",
            "bucket_name": self.bucket_name,
            "region_name": self.region_name,
            "supports_streaming": True,
            "supports_signed_urls": True,
            "supports_metadata": True,
            "url_expiration_default": self.url_expiration,
        }

    # File versioning methods (placeholder implementations)
    async def create_version(
        self, file_path: str, content: bytes, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new version of a file.

        Args:
            file_path: Path to the file
            content: File content
            metadata: Optional metadata for the version

        Returns:
            Version ID
        """
        # Placeholder implementation - S3 versioning would be implemented here
        import uuid

        version_id = str(uuid.uuid4())

        # Save the versioned file
        version_path = f"{file_path}/versions/{version_id}"
        await self.save_file(version_path, content, metadata)

        return version_id

    async def get_version(self, file_path: str, version: str) -> bytes:
        """Retrieve a specific version of a file.

        Args:
            file_path: Path to the file
            version: Version identifier

        Returns:
            File content for the specified version
        """
        # Placeholder implementation
        version_path = f"{file_path}/versions/{version}"
        content = await self.get_file(version_path)
        if content is None:
            raise FileNotFoundError(f"Version {version} not found for file {file_path}")
        return content

    async def list_versions(self, file_path: str) -> List[Dict[str, Any]]:
        """List all versions of a file.

        Args:
            file_path: Path to the file

        Returns:
            List of version information dictionaries
        """
        # Placeholder implementation
        versions_prefix = f"{file_path}/versions/"
        files = await self.list_files(prefix=versions_prefix)

        versions = []
        for file_info in files:
            version_id = file_info["path"].split("/")[-1]
            versions.append(
                {
                    "version_id": version_id,
                    "created_at": file_info["modified_at"],
                    "size": file_info["size"],
                    "checksum": file_info["checksum"],
                }
            )

        return versions

    async def delete_version(self, file_path: str, version: str) -> bool:
        """Delete a specific version of a file.

        Args:
            file_path: Path to the file
            version: Version identifier

        Returns:
            True if version was deleted, False otherwise
        """
        # Placeholder implementation
        version_path = f"{file_path}/versions/{version}"
        return await self.delete_file(version_path)

    async def get_latest_version(self, file_path: str) -> bytes:
        """Retrieve the latest version of a file.

        Args:
            file_path: Path to the file

        Returns:
            File content for the latest version
        """
        # Placeholder implementation
        versions = await self.list_versions(file_path)
        if not versions:
            raise FileNotFoundError(f"No versions found for file {file_path}")

        # Get the latest version (assuming they're sorted by creation time)
        latest_version = versions[-1]["version_id"]
        return await self.get_version(file_path, latest_version)
