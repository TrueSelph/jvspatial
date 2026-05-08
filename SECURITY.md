# Security Policy

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub
issues, discussions, or pull requests.**

If you believe you have found a security vulnerability in `jvspatial`,
report it privately to the maintainers:

- **Email:** `adminh@trueselph.com` with the subject line
  `[jvspatial security] <short summary>`
- **GitHub Security Advisories:** open a draft advisory at
  <https://github.com/TrueSelph/jvspatial/security/advisories/new>
  (preferred — gives us a private, audit-logged channel to coordinate a
  fix with you).

Please include, at minimum:

1. A description of the issue and the impact you believe it has.
2. The affected versions (if known) — see the supported-versions table
   below.
3. Steps to reproduce, or a minimal proof of concept.
4. Any suggested mitigations or patches you've already prototyped.

We acknowledge new reports within **5 business days**. For valid
reports we aim to ship a fix or a documented mitigation within **30
days** of acknowledgement, faster for high-severity issues.

We will credit reporters in the security advisory and the changelog
unless you ask us not to.

## Supported Versions

`jvspatial` follows [Semantic Versioning](https://semver.org/). Until
the project reaches 1.0, only the latest minor release receives
security fixes. Pre-1.0 minor versions are treated as breaking-change
boundaries: if a fix requires a breaking change in 0.x, we ship it in
the next minor.

| Version    | Supported          |
| ---------- | ------------------ |
| latest 0.x | :white_check_mark: |
| older 0.x  | :x:                |

After 1.0 we will support the current major and the previous major for
12 months past the previous major's last release.

## Scope

In scope:

- Code in the `jvspatial/` package as published to PyPI.
- Default configurations documented in the README and
  `docs/md/production-deployment.md`.

Generally out of scope (please report through normal issues):

- Issues that require an attacker who already has write access to the
  filesystem the application uses, the database the application is
  configured against, or the secrets the application is started with.
- Denial-of-service via deliberately oversized inputs to public APIs
  unless the bound is meaningfully smaller than the documented limits
  (e.g. a 1 KB request causing > 1 GB allocation).
- Vulnerabilities in transitive dependencies (please report those to
  the upstream project; we will pin / patch our own dependency
  metadata once the upstream releases a fix).
- Issues only reproducible against unsupported versions (see the
  table above).

## Embargo and Coordinated Disclosure

If you ask for an embargo, we will hold public disclosure until the
fix is released and adopters have a reasonable window to update —
typically 14 days for low/medium severity, longer by mutual agreement
for high/critical severity. We will publish the security advisory and
update the CHANGELOG simultaneously with the fix release.

## Cryptography and Secret Handling

`jvspatial` uses third-party cryptography (`PyJWT` for token signing,
`bcrypt` for password hashing). We do not implement primitives
in-house. If you discover a misuse of a primitive (wrong algorithm
choice, weak default parameters, secrets logged to disk), that is in
scope and we welcome the report.

## Hall of Fame

Reporters who responsibly disclose valid vulnerabilities will be
listed here once an advisory ships, unless they ask to remain
anonymous.
