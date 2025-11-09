# Storage Examples

This directory contains examples demonstrating jvspatial's file storage capabilities.

## Example Files

### storage_example.py
Comprehensive storage example demonstrating:
- Multiple backend support (Local and S3)
- File upload and download
- Storage configuration
- Error handling
- Metadata management
- Security features

### file_storage_demo.py
Basic file storage operations:
- File upload handling
- Download management
- File listing
- Metadata operations
- Proxy URL generation

## Storage Features

### Backend Support
- Local filesystem storage
- S3-compatible storage
- Custom storage backends

### File Operations
- Secure file uploads
- Streaming downloads
- Batch operations
- File verification
- Type validation

### URL Management
- Direct file URLs
- Proxy URL generation
- Expiring links
- One-time access URLs

### Security
- Path validation
- File type verification
- Size limitations
- Access control
- Secure configurations

## Usage Examples

### Local Storage
```python
from jvspatial.api import create_server

# Configure local storage
server = create_server(
    file_storage_enabled=True,
    file_storage_provider="local",
    file_storage_root=".files",
    proxy_enabled=True
)
```

### S3 Storage
```python
from jvspatial.api import create_server

# Configure S3 storage
server = create_server(
    file_storage_enabled=True,
    file_storage_provider="s3",
    s3_bucket_name="my-bucket",
    s3_region="us-east-1",
    proxy_enabled=True
)
```

### File Operations
```python
# Upload file
await storage.save_file("path/to/file.txt", content)

# Generate proxy URL
proxy_url = await server.create_proxy(
    file_path="path/to/file.txt",
    expires_in=3600  # 1 hour
)
```

## Best Practices

1. **Security**
   - Validate file types
   - Set size limits
   - Use secure configurations
   - Implement access control

2. **Performance**
   - Use appropriate chunk sizes
   - Implement caching
   - Handle large files properly
   - Monitor storage usage

3. **Error Handling**
   - Handle upload failures
   - Validate file integrity
   - Implement retry logic
   - Clean up partial uploads

4. **Configuration**
   - Use environment variables
   - Document storage paths
   - Set reasonable limits
   - Configure backup strategies

## Running Examples

```bash
# Run comprehensive storage example
python storage_example.py

# Run basic file operations demo
python file_storage_demo.py
```
