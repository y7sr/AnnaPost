# Contributing to AnnaPost

**Standalone Instagram Publishing System**

Thank you for your interest in contributing to AnnaPost! This document provides guidelines for contributing to the project.

**Last Updated:** 2026-08-11  
**Project Version:** 0.1.0

---

## Ways to Contribute

There are many ways to contribute to AnnaPost:

- **Reporting Bugs**: Open issues for bugs you find
- **Suggesting Features**: Share ideas for new features
- **Code Contributions**: Submit pull requests with bug fixes or new features
- **Documentation**: Improve existing docs or add new documentation
- **Testing**: Add new tests or improve existing ones
- **Code Review**: Review open pull requests
- **Security Reports**: Responsibly disclose security vulnerabilities

---

## Getting Started

### Prerequisites

- Python 3.12+
- uv (recommended) or pip
- Git

### Setting Up Development Environment

```bash
# Clone the repository
git clone <repo-url>
cd annapost

# Create virtual environment (optional, uv handles this)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -e ".[dev]"

# Or using make
make install

# Copy environment file
cp .env.example .env

# Edit .env with your local configuration

# Initialize database
alembic upgrade head

# Verify setup
uvicorn app.main:app --reload
# Visit http://localhost:8000/health
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific test file
pytest tests/unit/test_post_state_machine.py

# Run specific test
pytest tests/unit/test_post_state_machine.py::test_valid_transition

# Using make
make test
```

---

## Development Guidelines

### Code Style

AnnaPost uses `ruff` for linting and formatting. Follow these guidelines:

**Python Style:**
- Use Python 3.12+ features where appropriate
- Use type hints for all functions and variables
- Use `TypedDict` for dictionary structures
- Use `Literal` for string literals
- Use `@override` decorator for method overrides
- Follow PEP 8 style guide

**Formatting:**
```bash
# Format code
ruff format .

# Check style
ruff check .

# Auto-fix issues
ruff check --fix .
```

**Naming Conventions:**
- `snake_case` for variables, functions, files
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- `test_*` prefix for test functions

### Commit Messages

Use clear, descriptive commit messages:

```
feat: add new post creation endpoint
fix: prevent duplicate publishing in runner
chore: update dependencies
docs: add API documentation
refactor: extract media resolution logic
```

**Commit Message Format:**
- First line: 50 characters or less, imperative mood
- Body: Explanation of what and why (if needed)
- Footer: Reference issues, breaking changes (if applicable)

### Git Workflow

1. **Fork the repository** (if contributing externally)
2. **Create a feature branch**: `git checkout -b feature/your-feature`
3. **Make your changes**
4. **Run tests**: `pytest`
5. **Run linter**: `ruff check .`
6. **Commit changes**: `git commit -m "feat: your feature"`
7. **Push branch**: `git push origin feature/your-feature`
8. **Open Pull Request**

**Branch Naming:**
- `feat/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `chore/` - Maintenance tasks
- `test/` - Test-related changes

---

## Pull Request Guidelines

### Before Submitting

- [ ] All tests pass (`pytest`)
- [ ] Linter passes (`ruff check .`)
- [ ] Code is formatted (`ruff format .`)
- [ ] No new warnings or errors
- [ ] Documentation updated (if applicable)
- [ ] Tests added for new functionality

### Pull Request Template

```markdown
## Description

[Clear description of the change]

## Related Issues

[List any related issues]

## Changes Made

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Test coverage
- [ ] Refactoring
- [ ] Other

## Testing

- [ ] All existing tests pass
- [ ] New tests added
- [ ] Manual testing performed

## Checklist

- [ ] Code follows project style
- [ ] No breaking changes
- [ ] Documentation updated
- [ ] Tests pass
- [ ] Linter passes
```

### Review Process

1. **Code Review**: At least one maintainer must review and approve
2. **CI Checks**: All automated checks must pass
3. **Test Coverage**: New functionality must have tests
4. **Documentation**: Changes must be documented

---

## Architecture Guidelines

When contributing code, follow the existing architecture patterns:

### Layer Separation

**Do NOT:**
- Put business logic in API routes
- Put database logic in services
- Bypass the InstagramClient for HTTP calls
- Write directly to database from runners

**DO:**
- Use services for business logic
- Use repositories for database operations
- Use InstagramClient for Instagram API calls
- Use state machine for status transitions

### Idempotency

All operations must be idempotent. Use the atomic claim pattern:

```python
# Good: Atomic claim with rowcount check
rows_affected = await session.execute(
    update(Post)
    .where(Post.id == post_id)
    .where(Post.status.in_(eligible_statuses))
    .where(or_(Post.locked_at.is_(None), Post.locked_at < stale_cutoff))
    .values(status='publishing', locked_at=now, locked_by=worker_id)
)
if rows_affected.rowcount == 0:
    # Someone else claimed it, skip
    return
```

### Error Handling

Use the typed error hierarchy from `app/instagram/errors.py`:

```python
# Good: Use typed exceptions
try:
    await instagram_client.publish_container(container_id)
except InstagramTransientError as e:
    # Retry logic
    await handle_retry(e)
except InstagramValidationError as e:
    # Permanent error, don't retry
    raise PublishFailedError(str(e)) from e
```

### State Transitions

Always use the state machine for status changes:

```python
# Good: Validate transitions
from app.services.post_state_machine import validate_transition, PostStatus

validate_transition(
    from_status=PostStatus.READY,
    to_status=PostStatus.PUBLISHING,
    raise_on_invalid=True
)
```

---

## Testing Guidelines

### Test Structure

```
tests/
├── unit/          # Unit tests (isolated components)
├── integration/   # Integration tests (component interactions)
├── api/           # API endpoint tests
├── runners/       # Runner tests
└── ui/            # UI tests
```

### Test Writing

**Unit Tests:**
- Test individual functions in isolation
- Use mocking for external dependencies
- Test edge cases and error conditions

**Integration Tests:**
- Test interactions between components
- Use real database (test fixtures)
- Mock external APIs (Instagram)

**API Tests:**
- Test endpoint contracts
- Test validation
- Test error responses

**Runner Tests:**
- Test idempotency
- Test crash recovery
- Test concurrent execution

### Mocking Instagram API

Use `respx` for mocking Instagram HTTP calls:

```python
import respx
import httpx

async def test_publish_post():
    async with respx.mock:
        route = respx.post("https://graph.facebook.com/v18.0/...")
        route.return_value = httpx.Response(200, json={"id": "123"})
        
        result = await instagram_client.publish_container("123")
        assert route.called
        assert result == {"id": "123"}
```

### Test Coverage

Target **90%+** test coverage. Focus on:
- Critical paths (publishing, state transitions)
- Error handling
- Edge cases
- Concurrent operations

---

## Documentation Guidelines

### Code Documentation

**Module Level:**
```python
"""
Module documentation explaining purpose and usage.

Example:
    from app.services.posts import create_post
    await create_post(data)
"""
```

**Function Level:**
```python
def create_post(data: PostCreate) -> Post:
    """
    Create a new Instagram post.
    
    Args:
        data: Post creation data
        
    Returns:
        Created post
        
    Raises:
        ValidationError: If data is invalid
        NoDefaultAccountError: If no default account configured
    """
```

**Inline Comments:**
- Explain **why**, not **what**
- Avoid obvious comments
- Update comments when code changes

### API Documentation

API endpoints are automatically documented via OpenAPI. Ensure:
- Proper docstrings on route functions
- Accurate Pydantic schemas
- Examples where helpful

---

## Security Guidelines

### Security Checklist

Before contributing code that handles:

**User Input:**
- [ ] All inputs are validated
- [ ] SQL injection prevention (use ORM)
- [ ] XSS prevention (escape outputs)
- [ ] URL validation (http/https only)

**Tokens/Secrets:**
- [ ] Never stored in plaintext
- [ ] Never logged
- [ ] Never exposed in API responses
- [ ] Never exposed in error messages

**Database:**
- [ ] Use parameterized queries (SQLAlchemy ORM)
- [ ] Proper access controls
- [ ] Sensitive data encrypted

### Reporting Security Issues

**DO NOT** report security vulnerabilities in public issues or pull requests.

Instead, email security concerns to the maintainers privately.

---

## Performance Guidelines

### Database Queries

- Use indexes for frequent queries
- Avoid N+1 queries
- Keep transactions short
- Use async operations where possible

### Memory Usage

- Stream large responses
- Use generators for large datasets
- Avoid loading entire tables into memory

### Network Calls

- Use connection pooling
- Implement timeouts
- Handle failures gracefully
- Use retry with backoff

---

## Project Structure Reference

```
annapost/
├── app/
│   ├── main.py                    # FastAPI app
│   ├── admin/                     # Admin UI (Phase 4)
│   │   └── routes/
│   ├── api/
│   │   └── routes/                # API endpoints
│   ├── cli/                       # CLI commands
│   │   └── main.py
│   ├── core/                      # Core utilities
│   │   ├── config.py              # Configuration
│   │   ├── logging.py             # Logging
│   │   └── locking.py             # Locking utilities
│   ├── db/                        # Database
│   │   ├── base.py                # SQLAlchemy base
│   │   ├── session.py             # Session management
│   │   └── models/                # ORM models
│   ├── instagram/                 # Instagram client
│   │   ├── client.py              # API client
│   │   ├── errors.py              # Error types
│   │   ├── metrics.py             # Metric normalization
│   │   └── schemas.py             # Response schemas
│   ├── repositories/              # Database operations
│   ├── runners/                   # Job runners
│   └── services/                  # Business logic
├── alembic/                       # Database migrations
├── phases/                        # Phase documentation
├── tests/                         # Test suite
├── .env.example                   # Example environment
├── ARCHITECTURE.md                # Architecture reference
├── CLAUDE.md                     # AI assistant guidance
├── CONTRIBUTING.md               # This file
├── LICENSE
├── Makefile
├── plan.annapost.md               # Implementation plan
├── pyproject.toml                 # Project configuration
└── README.md
```

---

## Useful Commands

| Command | Description |
|---------|-------------|
| `make install` | Install dependencies |
| `make migrate` | Run migrations |
| `make run` | Run development server |
| `make test` | Run all tests |
| `make lint` | Run linter |
| `alembic upgrade head` | Apply migrations |
| `pytest` | Run tests |
| `ruff check .` | Check code style |
| `ruff format .` | Format code |

---

## Resources

- **Documentation**: See `README.md`, `ARCHITECTURE.md`
- **Implementation Plan**: `plan.annapost.md`
- **Phase Documentation**: `phases/`
- **Code Review**: `annapost-deep-code-review.md`
- **Issue Tracker**: [GitHub Issues](link-to-issues)
- **Discussions**: [GitHub Discussions](link-to-discussions)

---

## Code of Conduct

Be respectful and inclusive. Follow standard open source contribution guidelines:

- Respect different viewpoints
- Accept constructive criticism
- Focus on technical merit
- Be patient with new contributors

---

## License

By contributing to AnnaPost, you agree that your contributions will be licensed under the MIT License.

---

*Thank you for contributing to AnnaPost!*

*Last updated: 2026-08-11*