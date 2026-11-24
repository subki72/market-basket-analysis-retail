# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 1.0.x   | Yes       |
| < 1.0   | No        |

## Reporting a Vulnerability

If you discover a security vulnerability in this repository:

1. **Do NOT open a public GitHub issue** for undisclosed vulnerabilities.
2. Submit a private report via GitHub Security Advisories (`Security -> Advisories -> Report a vulnerability`).
3. Include affected file paths, line numbers, reproduction steps, and estimated severity.
4. Initial acknowledgement will be provided within **48 hours**.

## Security Controls

- **Secret Hygiene**: `.env`, `.env.*` (except `.env.example`), and key/certificate files are excluded via `.gitignore`; zero active credentials are stored in source control.
- **API Input & Abuse Protection**: Strict Pydantic v2 validation (`src/mba_engine/schemas.py`), item vocabulary caps (`MBA_MAX_ITEMS`), sliding-window rate limiting (`429`), CORS allowlist (`MBA_ALLOWED_ORIGINS`), defensive HTTP headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`), and a global exception boundary returning safe generic `500` JSON without stack trace exposure.
- **Safe CSV Parsing**: Precomputed `frozenset` rules in `MBA_Results_TopRules.csv` are parsed via `ast.literal_eval` without `eval()` or `pickle.loads()`.
- **Automated Scanning & Container Hardening**: Weekly Dependabot alerts (`semver-major` ignored for stability), Semgrep SAST (`p/python`), Trivy container image scanning in CI, and multi-stage non-root Docker execution (`appuser`, UID `10001`).
