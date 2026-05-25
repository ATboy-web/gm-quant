# Security Policy

## Supported Versions

| Version | Security Updates |
|---------|-----------------|
| V29.4   | 鉁?Active |
| V29     | 鉁?Active |
| V28     | 鈿狅笍 Critical fixes only |
| < V28   | 鉂?Unsupported |

## Reporting a Vulnerability

**Do NOT open a public issue** for security vulnerabilities.

Instead, please report them privately:

1. **Email**: Create a private security advisory through GitHub's Security tab
2. **Response time**: We aim to respond within 48 hours
3. **Disclosure**: We follow responsible disclosure 鈥?we'll publish after a fix is released

## Security Best Practices for Contributors

### Sensitive Data
- **NEVER commit API keys, tokens, or passwords** to the repository
- `push_to_github.py` in the repo uses a placeholder (`YOUR_GITHUB_PAT_HERE`)
- `config.py` should use environment variables or local-only files for `GM_TOKEN`

### GitHub PAT Protection
The repository has Secret Scanning enabled. Any commit containing:
- GitHub Personal Access Tokens (`ghp_*`)
- API keys matching common patterns
- Database connection strings

will be automatically blocked by GitHub's push protection.

### Dependency Security
- GM SDk `gm` package is the only external dependency
- Pin versions: `gm >= 3.0.183`
- Review GM SDK changelog before upgrading

### Code Review
- All PRs require at least one review
- Strategy changes must include backtest results
- Parameter changes must be documented in CHANGELOG.md

## What to Report

- Credentials accidentally exposed in the codebase
- Strategy logic that could cause financial loss in live trading
- Insecure handling of user data
- Dependency vulnerabilities

## What NOT to Report

- Backtest performance issues (use a regular Issue)
- Feature requests (use Feature Request template)
- Strategy parameter suggestions (use Discussion)

---

*Last updated: 2026-05-25 (V29.4)*
