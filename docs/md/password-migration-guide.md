# Password Hashing Migration Guide

jvspatial upgraded primary password hashing from SHA-256 to bcrypt. This guide explains the migration.

## Overview

- **Previous**: SHA-256 + salt for user passwords
- **Current**: bcrypt (with argon2/passlib fallbacks when bcrypt unavailable)
- **Migration**: Transparent — on successful login with a legacy SHA-256 hash, the password is automatically re-hashed with bcrypt

## No Action Required

Existing users are migrated automatically when they log in. No manual migration or user notification is needed.

## How It Works

1. On login, `AuthenticationService._verify_password()` detects legacy format (salt:hex)
2. If verification succeeds and bcrypt is available, the password is re-hashed with bcrypt
3. The updated hash is saved to the database
4. Future logins use bcrypt verification

## Fallback Behavior

If bcrypt is not installed (`pip install bcrypt`), the system falls back to argon2, then passlib, then SHA-256 with a warning. For production, install bcrypt:

```bash
pip install bcrypt
```

## Bootstrap Admin

When creating initial admin users, use `AuthenticationService.bootstrap_admin()` — it uses the current (bcrypt) hashing:

```python
from jvspatial.api.auth.service import AuthenticationService

auth_service = AuthenticationService(ctx, jwt_secret="...")
admin = await auth_service.bootstrap_admin("admin@example.com", "secure-password", "Admin")
```

## See Also

- [Authentication](authentication.md) - Auth system overview
- [Testing Guide](testing-guide.md) - Test auth setup
