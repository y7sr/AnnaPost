# Security Policy

**AnnaPost - Standalone Instagram Publishing System**

This document outlines security policies and practices for AnnaPost.

**Last Updated:** 2026-08-11  
**Version:** 0.1.0

---

## Security Overview

AnnaPost takes security seriously. This document provides guidance on:
- Security practices implemented in AnnaPost
- Security considerations for deployments
- How to report security vulnerabilities
- Security checklist for contributors

---

## Implemented Security Measures

### Authentication & Authorization

**Current State:** No authentication for local/trusted deployments (as per design in `plan.annapost.md` section 31)

**Rationale:**
- Initial deployment is trusted/local
- Admin UI under `/admin` prefix to allow future auth without affecting `/api/v1`
- Authentication can be added when API becomes remotely accessible

**Future Considerations:**
- API authentication (JWT, OAuth2, API keys)
- Session management
- Role-based access control (RBAC)

### Token Security

**Implementation:**
- Access tokens are **never stored in plaintext** in the database
- Tokens stored as references (`access_token_ref`) in `instagram_accounts` table
- The current resolver accepts only `env:VARIABLE_NAME` references; plaintext
  values and other reference schemes are rejected
- Actual tokens live in the process environment or ignored `.env`, never in
  command arguments, database rows, repository files, or logs

**Token Handling:**
```python
# Good: Token reference stored, not actual token
account.access_token_ref = "env:INSTAGRAM_ACCESS_TOKEN"

# Bad: Never store actual tokens
account.access_token = "actual-token-value"  # ❌ NEVER DO THIS
```

**Token Protection:**
- Never exposed in API responses
- Never logged (even in debug mode)
- Never included in error messages
- Never stored in source control

### Temporary Local Media Exposure

`python -m app.cli.main posts publish-file ... --confirm` may expose one local
image through a Cloudflare Quick Tunnel so Instagram can fetch it. The command
is constrained as follows:

- It validates that the target is a regular image file before starting a server.
- `SingleFileServer` binds only to `127.0.0.1`, uses a random route, and serves
  only the selected file via `GET` or `HEAD`; it offers no directory listing or
  arbitrary-path access.
- The original filename is not included in the public URL.
- `cloudflared` runs only for the publication attempt and is terminated during
  cleanup, including failure paths.
- The command requires `--confirm`; it is an external, irreversible write.
- Failed ephemeral publication jobs are canceled before teardown. They are not
  automatically retried after the temporary URL disappears.

This is intentionally not a general file-serving endpoint, object store, or
durable source for scheduled posts. A durable HTTPS source is required when a
publication or retry must outlive the CLI process.

### Input Validation

**URL Validation:**
- All external URLs are validated before use
- Only `http` and `https` schemes are allowed
- URL length and format validation
- Protection against SSRF (Server-Side Request Forgery)

**Media Source Validation:**
```python
from urllib.parse import urlparse
from app.instagram.errors import InstagramValidationError

def validate_media_url(url: str) -> None:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise InstagramValidationError(f"Invalid URL scheme: {parsed.scheme}")
        if not parsed.netloc:
            raise InstagramValidationError("Missing hostname in URL")
        if len(url) > 2048:  # Reasonable URL length limit
            raise InstagramValidationError("URL too long")
    except ValueError as e:
        raise InstagramValidationError(f"Invalid URL: {e}") from e
```

### Database Security

**SQL Injection Protection:**
- SQLAlchemy ORM provides parameterized queries
- Never use raw SQL with string formatting
- Always use ORM methods or parameterized queries

**Example:**
```python
# Good: ORM with parameterized queries
from sqlalchemy import select
from app.db.models.post import InstagramPost

result = await session.execute(
    select(InstagramPost).where(InstagramPost.id == post_id)
)

# Bad: String formatting in queries (SQL INJECTION RISK)
cursor.execute(f"SELECT * FROM posts WHERE id = {post_id}")  # ❌ NEVER DO THIS
```

**Data Encryption:**
- Consider encrypting sensitive data at rest
- Use SQLCipher for SQLite encryption if needed
- Store encryption keys in secure location

### Error Handling

**Error Sanitization:**
- Error messages never leak sensitive information
- Stack traces not exposed in production
- Internal paths and configuration not revealed

**Example:**
```python
# Good: Sanitized error message
from fastapi import HTTPException

try:
    await instagram_client.publish_container(container_id)
except InstagramAuthenticationError:
    # Don't expose token information
    raise HTTPException(
        status_code=401,
        detail="Authentication failed. Please check your Instagram account configuration."
    )

# Bad: Leaking sensitive information
raise HTTPException(
    status_code=401,
    detail=f"Token expired: {access_token}"  # ❌ NEVER DO THIS
)
```

### Network Security

**HTTPS:**
- Always use HTTPS in production
- Use valid SSL/TLS certificates
- Consider HSTS headers

**HTTPX Client Configuration:**
- Configure timeouts to prevent hanging
- Use connection pooling
- Validate SSL certificates
- Set custom user agent for identification

```python
# Good: Secure HTTPX client configuration
import httpx
from app.core.config import settings

client = httpx.AsyncClient(
    timeout=httpx.Timeout(10.0, connect=5.0),
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    verify=True,  # SSL verification
    headers={"User-Agent": "AnnaPost/0.1.0"}
)
```

### Logging Security

**Sensitive Data:**
- Never log access tokens
- Never log secrets or credentials
- Never log large raw payloads unnecessarily
- Never log personal data without consent

**Structured Logging:**
```python
# Good: Structured logging without sensitive data
import logging
from app.core.logging import get_logger

logger = get_logger(__name__)

logger.info(
    "Publish started",
    extra={
        "post_id": post_id,
        "account_id": account_id,
        "operation": "publish",
        # NEVER include: access_token, secret, token_ref, etc.
    }
)
```

### Security Headers

**API Security Headers:**
- Consider adding security headers to API responses
- Use FastAPI middleware for header injection

**Recommended Headers:**
```python
from fastapi import FastAPI
from fastapi.middleware.security import SecurityHeadersMiddleware

app = FastAPI()

# Add security headers
app.add_middleware(
    SecurityHeadersMiddleware,
    content_security_policy="default-src 'self'",
    force_https=True,
    frame_options="DENY",
    content_type_nosniff=True,
    strict_transport_security="max-age=63072000; includeSubDomains; preload"
)
```

---

## Security Checklist

### For Contributors

Before submitting code, verify:

#### Input Validation
- [ ] All external inputs are validated
- [ ] URLs are validated (scheme, length, format)
- [ ] Media sources are validated
- [ ] File paths are validated (no directory traversal)
- [ ] SQL queries use parameterized queries (ORM)

#### Token/Secret Handling
- [ ] No tokens stored in plaintext
- [ ] No tokens in API responses
- [ ] No tokens in logs
- [ ] No tokens in error messages
- [ ] No tokens in source control
- [ ] Token references used (not actual tokens)

#### Error Handling
- [ ] Error messages don't leak sensitive information
- [ ] Stack traces not exposed in production
- [ ] Internal paths not revealed
- [ ] Configuration not exposed

#### Database
- [ ] Parameterized queries used (no string formatting)
- [ ] SQL injection prevention in place
- [ ] Sensitive data handled securely

#### Network
- [ ] Timeouts configured for HTTP clients
- [ ] SSL verification enabled
- [ ] Connection pooling configured
- [ ] User agent set for identification

#### Logging
- [ ] No sensitive data in logs
- [ ] Structured logging used
- [ ] Log levels appropriate
- [ ] No large payloads logged

---

## Deployment Security

### Environment Configuration

**Environment Variables:**
- Keep secrets in environment variables
- Use `.env.example` for documentation (never commit `.env`)
- Rotate secrets regularly

**Example `.env.example`:**
```bash
# Database
DATABASE_URL=sqlite+aiosqlite:///./annapost.db

# Instagram API
INSTAGRAM_GRAPH_API_VERSION=v18.0

# Security
LOCK_STALE_AFTER_SECONDS=600
LOG_LEVEL=INFO

# Secret references (not actual secrets)
# INSTAGRAM_ACCESS_TOKEN_REF=secret-manager:token-123
```

### Database Security

**SQLite Deployment:**
- File permissions: `chmod 600 annapost.db`
- Directory permissions: `chmod 700` for database directory
- Consider filesystem encryption

**Backup:**
- Regular database backups
- Test restore procedures
- Secure backup storage

### Network Security

**Firewall Rules:**
- Restrict access to API ports
- Allow only trusted IPs for admin access
- Rate limiting for API endpoints

**Rate Limiting:**
- Implement rate limiting for API endpoints
- Use FastAPI middleware or proxy-level rate limiting
- Configure appropriate limits based on use case

### Secrets Management

**Options:**
1. **Environment Variables**: Simple but limited
2. **Secret Manager**: AWS Secrets Manager, HashiCorp Vault, etc.
3. **Encrypted Files**: Ansible Vault, SOPS, etc.
4. **Kubernetes Secrets**: For containerized deployments

**Example with Secret Manager:**
```python
import httpx
from app.core.config import settings

async def get_access_token(account_ref: str) -> str:
    """Retrieve access token from secure storage."""
    # Implement based on your secrets manager
    # This is just a placeholder example
    if account_ref.startswith("secret-manager:"):
        token_id = account_ref.replace("secret-manager:", "")
        return await fetch_from_secret_manager(token_id)
    else:
        raise ValueError("Invalid token reference")
```

---

## Security Testing

### Static Analysis

**Bandit (Python Security Linter):**
```bash
pip install bandit
bandit -r app/ -ll  # Low severity and above
```

**Safety (Dependency Vulnerability Scanner):**
```bash
pip install safety
safety check
```

### Dynamic Testing

**OWASP ZAP:**
- Automated security scanning
- API security testing
- Vulnerability detection

**Manual Testing:**
- Test with malicious inputs
- Test edge cases
- Test error conditions
- Test concurrent access

---

## Security Vulnerability Reporting

### How to Report

**DO NOT** report security vulnerabilities in public issues or pull requests.

Instead, email security concerns to the maintainers privately:

**Email:** [security email - to be configured]

**Include:**
- Description of the vulnerability
- Steps to reproduce
- Impact assessment
- Suggested fix (if any)

### Response Process

1. **Acknowledgment**: Initial response within 48 hours
2. **Triage**: Assessment of severity and impact
3. **Fix**: Development of patch or mitigation
4. **Disclosure**: Coordinated disclosure (if applicable)
5. **Release**: Security fix in next release

### Severity Levels

| Severity | Description | Response Time |
|----------|-------------|---------------|
| Critical | Remote code execution, data breach | Immediate (24 hours) |
| High | Authentication bypass, privilege escalation | 3 days |
| Medium | Information disclosure, DoS | 1 week |
| Low | Minor security issues | Next release |

---

## Security Updates

### Version History

| Version | Date | Security Improvements |
|---------|------|---------------------|
| 0.1.0 | 2026-08-11 | Initial security practices, token handling, input validation |

### Security Advisories

None at this time.

---

## Resources

### Security Standards
- [OWASP Top 10](https://owasp.org/Top10/)
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [CWE/SANS Top 25](https://cwe.mitre.org/top25/)

### Tools
- [Bandit](https://bandit.readthedocs.io/) - Python security linter
- [Safety](https://pyup.io/safety/) - Dependency vulnerability scanner
- [OWASP ZAP](https://www.zaproxy.org/) - Security scanner
- [Trivy](https://github.com/aquasecurity/trivy) - Container scanning

---

## Contact

For security questions or concerns:
- **General Inquiries**: See project documentation
- **Security Reports**: Email maintainers privately
- **Bug Reports**: Open GitHub issue
- **Feature Requests**: Open GitHub issue

---

*This security policy is effective as of 2026-08-11 for AnnaPost v0.1.0*
