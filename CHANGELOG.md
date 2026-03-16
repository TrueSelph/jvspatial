# Changelog

All notable changes to jvspatial will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- **BREAKING**: JWT secret must be set explicitly when authentication is enabled. The server now fails fast with a clear error if `JVSPATIAL_JWT_SECRET_KEY` is not set or uses a placeholder value. Set via environment or `Server(auth=dict(jwt_secret="..."))`.
- Add security headers middleware (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection) applied to all responses by default. Configurable via `Server(security=dict(security_headers_enabled=True))`.
- AuthConfig `jwt_secret` default changed from `"your-secret-key"` to empty string; explicit setting required when auth is enabled.
- Remove duplicate `/auth/register` from auth exempt paths.

### Added

- `SecurityConfig` with `security_headers_enabled` option.
- [Production Deployment Guide](docs/md/production-deployment.md) with security checklist.
- CI now runs test coverage with `--cov-fail-under=50`.

### Changed

- Security headers are applied automatically (enabled by default).

## [0.0.5] - Previous

See git history for changes before this release.
