# jvspatial/storage

File storage system: interfaces, security layer, version model, URL proxy manager.

> **Read first**: [SPEC §12](../../SPEC.md), [docs/md/file-storage-architecture.md](../../docs/md/file-storage-architecture.md)

---

## Purpose

`storage/` provides a secure abstraction over file backends. Every upload passes a five-stage path sanitizer and a content-based MIME validator before reaching the backend. Local-filesystem and S3 backends ship today; the interface is open for additional providers.

## Layout

```
storage/
├── interfaces/
│   ├── base.py             # FileStorageInterface ABC
│   ├── local.py            # LocalFileInterface
│   └── s3.py               # S3FileInterface (optional extra)
├── security/
│   ├── path_sanitizer.py   # Five-stage validation
│   └── validator.py        # Content-based MIME validation
├── managers/
│   ├── proxy.py            # URL proxy lifecycle
│   └── *.py                # Other management helpers
├── models.py               # Pydantic file/version/proxy models
└── exceptions.py           # Storage-specific exceptions
```

## Public API (from `jvspatial.storage`)

| Name | What it does |
|---|---|
| `create_storage(provider, **kwargs)` | Factory entry point (provider ∈ `local`, `s3`) |
| `create_default_storage()` | Env-driven default (`JVSPATIAL_FILE_INTERFACE`) |
| `FileStorageInterface` | ABC for storage backends |
| `LocalFileInterface` | Filesystem backend |
| `S3FileInterface` | S3 backend (requires boto3) |
| `PathSanitizer` | Path validation |
| `FileValidator` | MIME / size validation |
| `URLProxy`, `URLProxyManager`, `get_proxy_manager` | Time-limited / one-time download URLs |
| `StorageError`, `PathTraversalError`, `InvalidPathError`, `ValidationError`, `FileNotFoundError`, `FileSizeLimitError`, `InvalidMimeTypeError`, `StorageProviderError`, `AccessDeniedError` | Exception types |

## Invariants

- **Every upload passes `PathSanitizer` then `FileValidator`.** No bypass for "trusted" callers. (`security/path_sanitizer.py`, `security/validator.py`)
- **MIME validation is content-based, not extension-based.** Uses `python-magic`. Renaming `.exe` → `.txt` does not bypass blocking.
- **Path sanitization is five stages**: regex blocklist → normalization with re-check → hidden-file allowlist → symlink resolution → base-dir confinement.
- **Internal directory markers bypass user-input checks via metadata only.** Not via filenames. (`storage/security/path_sanitizer.py`)
- **Atomic writes for local backend.** Same `temp + fsync + rename + fsync(dir)` helper as JsonDB.
- **S3 multipart at ≥8 MiB.** Configurable via constructor or `JVSPATIAL_S3_MULTIPART_THRESHOLD`.
- **S3 throttle retry** uses the shared retry helper with exponential backoff + jitter.

## Modification patterns

- **Adding a backend**: implement `FileStorageInterface`. Wire into `create_storage(provider="...")` and the storage manager. Add tests under `tests/storage/`.
- **Changing path sanitization**: review all five stages; add tests to `tests/storage/test_path_sanitizer.py`. Each stage has its own test surface.
- **Extending allowed MIME types**: update `FileValidator.ALLOWED_MIME_TYPES` and add an integration test that round-trips the new type.
- **Adding a security rule**: prefer adding to the sanitizer (paths) or validator (content) rather than ad-hoc in the backend.

## Related docs

- [docs/md/file-storage-architecture.md](../../docs/md/file-storage-architecture.md)
- [docs/md/file-storage-usage.md](../../docs/md/file-storage-usage.md)
- [docs/md/security-review.md](../../docs/md/security-review.md)
- [docs/md/security-operational-notes.md](../../docs/md/security-operational-notes.md)

## Stability

`create_storage`, `FileStorageInterface`, `LocalFileInterface`, `S3FileInterface`, the security classes, and the exception hierarchy are public. `managers/` internals can change between minor versions; cross them through `get_proxy_manager` and the documented API.
