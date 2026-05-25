# Security Policy

## Supported Versions

| Version | Security Updates |
|---------|-----------------|
| V29.4   | ✅ Active |
| V29     | ✅ Active |
| V28     | ⚠️ Critical fixes only |
| < V28   | ❌ Unsupported |

## Reporting a Vulnerability

**Do NOT open a public issue** for security vulnerabilities.

Instead, use GitHub's private Security Advisory feature:

👉 **[Report a Vulnerability](https://github.com/ATboy-web/gm-quant/security/advisories/new)**

1. Go to **Security → Advisories → Report a vulnerability**
2. Describe the vulnerability in detail (steps to reproduce, affected versions)
3. **Response time**: We aim to acknowledge within 48 hours and fix within 7 days
4. **Disclosure**: We follow responsible disclosure — the advisory will be published after a fix is released
5. **Credit**: We're happy to credit researchers in the advisory (opt-in)

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
- **GM SDK** (`gm >= 3.0.183`) is the only external runtime dependency for backtesting
- `numpy`, `pandas`, `matplotlib` are pinned in `setup.py`
- Review [GM SDK changelog](https://www.myquant.cn/docs) before upgrading
- Run `pip list --outdated` periodically to check for vulnerable packages

### Token & Credential Hygiene
- The repo uses `YOUR_GITHUB_PAT_HERE` placeholder in `push_to_github.py`
- `config.py` uses a placeholder `GM_TOKEN = ''` — fill in locally, never commit
- Any PR that accidentally includes a real token will be blocked by Secret Scanning
- If you've accidentally exposed a token, **revoke it immediately** at [GitHub Tokens](https://github.com/settings/tokens)

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
