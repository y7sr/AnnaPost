# AnnaPost

**Standalone Instagram Publishing System**

**Document Type:** Project Documentation | **Version:** 0.1.0 | **Status:** Phase 3 Implementation Complete | **Last Updated:** 2026-08-11

---

## AI OPTIMIZATION SUMMARY

```yaml
PURPOSE: Main entry point for project understanding
FORMAT: Hierarchical, structured information
TARGET: Developers, AI assistants, contributors
PRIORITY: Overview first, then setup, then details
```

---

## PROJECT OVERVIEW

### What is AnnaPost?
AnnaPost is a robust, standalone system for publishing and managing content on Instagram. It provides a complete solution for scheduling, publishing, syncing metrics, managing comments, and handling deletions - all through a clean API interface.

### Key Characteristics
- **Bounded integration:** Optional authenticated Vend1r bridge; AnnaPost still
  owns post persistence, jobs, and Instagram credentials.
- **Multi-Account:** Built for multiple Instagram accounts from day one
- **Idempotent:** Safe to retry operations - prevents duplicate publishing
- **Self-Contained:** Uses SQLite as both database and queue (no external dependencies)
- **Production-Ready:** Phase 3 implementation complete, Phase 4 UI in progress

### Current Status
- ✅ **Phase 1:** Skeleton (FastAPI, SQLite, Alembic, health endpoint)
- ✅ **Phase 2:** Architecture (Data model, state machine, contracts, migrations)
- ✅ **Phase 3:** Implementation (Services, API, runners, CLI)
- 🟡 **Phase 4:** UI (Admin dashboard with Jinja2 + HTMX)
- ❌ **Phase 5:** Review (Full test suite, hardening, audit)

---

## QUICK START

### Prerequisites
- Python 3.12+
- uv (recommended) or pip

### Installation

#### 1. Clone and Setup
```bash
# Clone the repository
git clone <repo-url>
cd annapost

# Create environment file from example
cp .env.example .env
```

#### 2. Environment Configuration
```bash
# Required settings (edit .env)
DATABASE_URL=sqlite+aiosqlite:///./annapost.db
INSTAGRAM_GRAPH_API_VERSION=v18.0
LOCK_STALE_AFTER_SECONDS=600
LOG_LEVEL=INFO

# Optional settings
DEBUG=False

# Optional Vend1r bridge
VEND1R_BRIDGE_BASE_URL=http://127.0.0.1:8701
VEND1R_BRIDGE_WORKSPACE_ID=default
ANNAPOST_BRIDGE_TOKEN=
```

#### 3. Install Dependencies
```bash
# Using uv (recommended)
uv pip install -e ".[dev]"

# Alternative with pip
pip install -e ".[dev]"
```

#### 4. Initialize Database
```bash
# Apply all migrations
alembic upgrade head
```

### Running the Application
```bash
# Development server with auto-reload
uvicorn app.main:app --reload

# Production server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The application will be available at `http://localhost:8000`

---

## USAGE

### API Documentation

Once running, access the interactive API documentation:
- **OpenAPI Docs:** `http://localhost:8000/docs`
- **Redoc:** `http://localhost:8000/redoc`

### Health Check
```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### API Endpoints Overview

#### Accounts Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/accounts` | List all accounts |
| POST | `/api/v1/accounts` | Create a new account |
| GET | `/api/v1/accounts/{id}` | Get account details |
| PATCH | `/api/v1/accounts/{id}` | Update account |

#### Posts Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/posts` | List all posts |
| POST | `/api/v1/posts` | Create a new post |
| GET | `/api/v1/posts/{id}` | Get post details |
| PATCH | `/api/v1/posts/{id}` | Update post |
| POST | `/api/v1/posts/{id}/schedule` | Schedule a post |
| POST | `/api/v1/posts/{id}/publish` | Publish a post immediately |
| DELETE | `/api/v1/posts/{id}` | Soft delete a post (requests remote deletion) |
| GET | `/api/v1/posts/{id}/metrics` | Get post metrics |
| GET | `/api/v1/posts/{id}/comments` | Get post comments |
| POST | `/api/v1/posts/{id}/comments` | Create a comment on a post |

#### Comments Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/comments/{id}/reply` | Reply to a comment |

#### Jobs Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/jobs` | List all jobs |

#### Events Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/events` | List all events |

#### Global Options
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/options` | List all global options |
| PATCH | `/api/v1/options/{key}` | Update a global option |

### Admin Dashboard
Access the admin dashboard at `http://localhost:8000/admin`

**Dashboard Features:**
- Account management (CRUD, default account selection)
- Post creation and management (with status filtering)
- Job monitoring (type/status filters, retry/cancel actions)
- Event timeline (read-only per account/post)
- Metrics visualization (historical snapshots with charts)
- Comment moderation (inbox, outgoing queue, reply forms)

### Runners
Runners are external entry points that process queued work. They are designed to be invoked externally (via cron, systemd, launchd, or manual execution).

```bash
# Publish due posts
python -m app.runners.publish

# Sync metrics and comments from published posts
python -m app.runners.sync

# Process queued actions (delete, comment, reply)
python -m app.runners.actions
```

**Runner Characteristics:**
- **Idempotent:** Safe to run frequently
- **Self-Determining:** Runners determine if work is due
- **Non-Blocking:** Short transactions, no long-running operations
- **Crash-Safe:** Designed for recovery and restart

### CLI Commands

#### Account Management
```bash
# List accounts
python -m app.cli.main accounts list
```

#### Post Management
```bash
# List posts
python -m app.cli.main posts list

# Show post details
python -m app.cli.main posts show <id>
```

#### Job Management
```bash
# List jobs
python -m app.cli.main jobs list
```

#### Runner Execution
```bash
# Poll Vend1r and import eligible drafts/desired posts; does not publish
python -m app.cli.main runner bridge

# Run publish runner
python -m app.cli.main runner publish

# Run sync runner
python -m app.cli.main runner sync

# Run actions runner
python -m app.cli.main runner actions

```

The bridge runner is safe to invoke repeatedly and does not call Instagram.
It polls the Vend1r workspace configured by `VEND1R_BRIDGE_WORKSPACE_ID`,
imports media into `data/media`, and only queues publication when Vend1r sends
`ready`. `draft` and `do_not_publish` never create a publish job. Scheduling is
external (manual, cron, launchd, or systemd); AnnaPost does not run a built-in
cron loop.

### Publish a Local Image with ngrok

`posts publish-file` is the one-shot path for a local image. It makes a real,
irreversible Instagram post only when `--confirm` is present.

#### Preconditions

- Run from the repository root with the project environment active.
- `ngrok` must be available on `PATH` and authenticated; the command starts a
  temporary HTTPS tunnel and discovers its local inspector endpoint.
- The image must be a regular local file whose filename maps to an `image/*`
  MIME type (for example `.jpg`, `.jpeg`, `.png`, or `.webp`).
- The target account must be enabled and have `instagram_user_id` plus an
  `access_token_ref` of the form `env:VARIABLE_NAME`. That environment variable
  must be set without printing it. If `--account-id` is omitted, the enabled
  default account is used.

Create or update the account through `/docs`, the Admin UI, or the account API.
For example, this request changes local AnnaPost account configuration and
demotes any current default account; it does not publish anything:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/accounts \
  -H 'content-type: application/json' \
  -d '{
    "name": "primary",
    "instagram_user_id": "INSTAGRAM_USER_ID",
    "is_default": true,
    "enabled": true,
    "access_token_ref": "env:INSTAGRAM_ACCESS_TOKEN"
  }'
```

#### Command

```bash
python -m app.cli.main posts publish-file ./image.jpg \
  --caption "Caption" \
  --account-id 1 \
  --confirm
```

Omit `--account-id` to use the enabled default account.

#### Runtime Behavior and Safety Boundary

1. The CLI validates the account and local file before exposing anything.
2. It serves only that one file on `127.0.0.1` under a random, unguessable URL.
   Directory listing and arbitrary local paths are unavailable; only `GET` and
   `HEAD` for that route return the image.
3. It starts an ngrok HTTP tunnel and waits up to 30 seconds for its HTTPS URL.
4. It creates a URL-backed image post, queues it, and runs only that exact job.
   It never consumes other pending publish jobs.
5. It prints a JSON receipt with `post_id`, `job_id`, post status, media ID,
   permalink, and any recorded publish error; then it stops the tunnel and
   loopback server.

The public URL is intentionally temporary. If publishing fails, the pending
one-shot job is canceled before cleanup so that an automatic retry cannot fetch
from a dead URL. The post and its event history remain available for diagnosis.
For scheduled posts and long-running retries, use AnnaPost-managed durable media
or a durable HTTPS URL. Object storage remains a future resolver, and this
command itself currently publishes a single image only; it is not an S3
replacement.

#### Verified live retry behavior

On 2026-08-13, post `12` was published successfully through the durable
`local_file` runner path using a fresh temporary ngrok tunnel. The first
`media_publish` attempt returned Instagram's `Media ID is not available` error;
the container later reported `FINISHED`, and an explicit retry reused that
persisted container and completed successfully. The resulting post was
[published on Instagram](https://www.instagram.com/p/Db-AvuXjmih/).

This confirms that a failed publish may be retried safely after inspecting the
post, job, and remote container state. The retry reuses the persisted
`instagram_container_id`; it must not blindly create a second container.

### Live Insights and Comment Reads

Source of truth: `app/instagram/client.py`, `app/instagram/metrics.py`,
`app/services/sync.py`, and the provider response at the time of a read. The
metrics and comments API endpoints return AnnaPost's stored observations; run
the sync runner to refresh them. A numeric `0` means Instagram explicitly
reported zero; `NULL` means unavailable and must never be rendered as zero.

Provider verification on 2026-08-12 for a Feed image confirmed these lifetime
Insights metrics are available individually: `views`, `reach`,
`total_interactions`, `likes`, `comments`, `shares`, `saved`,
`profile_activity`, `follows`, and `profile_visits`. `reposts` was explicitly
rejected by the Instagram Media Insights endpoint for that post type.

**Current integration gap:** this provider verification used explicit
per-metric requests. `InstagramClient.get_media_insights()` currently makes a
generic Insights request, so its compatibility with the provider's current
per-metric shape is **Unknown**. Verify or adapt that client call before
claiming that `runner sync` stores every metric listed above.

Do not infer readable comment content from `comments_count`. The provider can
report a non-zero count while `/{media-id}/comments` returns an empty `data`
array. Treat that as a provider/token visibility limitation; retain the count,
but do not manufacture authors or text. Revalidate the token's comment
permissions and the provider response before diagnosing a missing comment.

---

## ARCHITECTURE OVERVIEW

### Core Principle
```
External Producer → FastAPI API → Database → Runners → InstagramClient → Instagram Graph API

DATABASE = desired state + internal history
INSTAGRAM = external state
RUNNERS = reconciliation between both
```

### Layered Architecture
```
┌─────────────────────────────────────────────────────────┐
│                    API Layer (FastAPI)                      │
│  app/api/routes/ - Thin HTTP layer, validation, status     │
├─────────────────────────────────────────────────────────┤
│                    Admin UI Layer                           │
│  app/admin/routes/ - Template-based admin interfaces       │
├─────────────────────────────────────────────────────────┤
│                  Services Layer                             │
│  app/services/ - Business logic, state transitions        │
├─────────────────────────────────────────────────────────┤
│                 Repositories Layer                          │
│  app/repositories/ - Query helpers, database operations    │
├─────────────────────────────────────────────────────────┤
│                   Database Layer                            │
│  app/db/models/ - SQLAlchemy ORM models                   │
│  app/db/session/ - Connection management                   │
├─────────────────────────────────────────────────────────┤
│               Instagram Client Layer                        │
│  app/instagram/ - Graph API abstraction, error handling   │
├─────────────────────────────────────────────────────────┤
│                    Runners Layer                            │
│  app/runners/ - External entry points, job execution      │
├─────────────────────────────────────────────────────────┤
│                      CLI Layer                              │
│  app/cli/ - Command-line interface                         │
└─────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

| Decision | Rationale | Implementation |
|----------|-----------|----------------|
| SQLite as Queue | No external dependencies | Job tables in SQLite |
| Atomic Claim Pattern | Prevents duplicate processing | Conditional UPDATE + rowcount check |
| Short Transactions | No SQLite write transaction spans HTTP call | Commit after claim, before HTTP |
| State Machine | Explicit transition rules | `app/services/post_state_machine.py` |
| Single Instagram Client | Centralized Graph API abstraction | `app/instagram/client.py` |
| Event Sourcing | Application history | Append-only `instagram_events` table |

---

## CONFIGURATION

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Database connection URL | `sqlite+aiosqlite:///./annapost.db` |
| `INSTAGRAM_GRAPH_API_VERSION` | Instagram Graph API version | `v18.0` |
| `LOCK_STALE_AFTER_SECONDS` | Stale lock timeout in seconds | `600` (10 minutes) |
| `VEND1R_BRIDGE_BASE_URL` | Vend1r bridge base URL | `http://127.0.0.1:8701` |
| `VEND1R_BRIDGE_WORKSPACE_ID` | Vend1r workspace polled by the bridge | `default` |
| `ANNAPOST_BRIDGE_TOKEN` | Shared server-to-server bridge token | unset |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DEBUG` | Enable debug mode | `False` |

### Database Options (Global Options Table)
These settings can be modified at runtime via the API or CLI:

| Key | Description | Default |
|-----|-------------|---------|
| `default_sync_intervals` | Sync frequency configuration | `{"new": 3600, "active": 86400, "old": 604800}` |
| `publish_batch_size` | Number of posts to process per batch | `10` |
| `sync_batch_size` | Number of posts to sync per batch | `10` |
| `max_retry_count` | Maximum retry attempts for jobs | `5` |
| `retry_backoff` | Retry backoff sequence (seconds) | `[60, 300, 900, 3600]` |
| `default_account_id` | ID of the default account | `null` |

---

## PROJECT STRUCTURE

### Directory Layout
```
annapost/
├── app/
│   ├── main.py                    # FastAPI application entry point
│   ├── admin/                     # Admin UI routes and templates
│   │   ├── routes/                # Admin route handlers
│   │   └── templates/             # Jinja2 HTML templates
│   ├── api/
│   │   └── routes/                # API route handlers
│   │       ├── accounts.py
│   │       ├── comments.py
│   │       ├── events.py
│   │       ├── jobs.py
│   │       ├── metrics.py
│   │       ├── options.py
│   │       └── posts.py
│   ├── cli/                       # Command-line interface
│   │   └── main.py
│   ├── core/
│   │   ├── config.py              # Configuration settings
│   │   └── logging.py             # Logging configuration
│   ├── db/
│   │   ├── base.py                # SQLAlchemy base
│   │   ├── session.py             # Database session management
│   │   └── models/                # ORM models
│   ├── instagram/
│   │   ├── client.py              # Instagram Graph API client
│   │   ├── errors.py              # Typed error hierarchy
│   │   ├── metrics.py             # Metric normalization
│   │   └── schemas.py             # Instagram response schemas
│   ├── repositories/
│   │   ├── accounts.py
│   │   ├── comments.py
│   │   ├── jobs.py
│   │   ├── metrics.py
│   │   └── posts.py
│   ├── runners/
│   │   ├── __init__.py
│   │   ├── actions.py             # Action runner
│   │   ├── publish.py             # Publish runner
│   │   └── sync.py                # Sync runner
│   └── services/
│       ├── accounts.py
│       ├── actions.py
│       ├── comments.py
│       ├── media.py
│       ├── post_state_machine.py
│       ├── publishing.py
│       ├── reconciliation.py
│       └── sync.py
├── alembic/                       # Database migrations
│   ├── env.py
│   └── versions/
│       ├── 001_initial_schema.py
│       └── 002_add_indexes.py
├── phases/                        # Phase documentation
│   ├── 01-prebuild.md
│   ├── 02-architecture.md
│   ├── 03-implementation.md
│   ├── 04-ui.md
│   └── 05-review.md
├── tests/                         # Test suite
│   ├── api/
│   ├── integration/
│   ├── runners/
│   ├── ui/
│   └── unit/
├── .env.example                   # Example environment file
├── .gitignore
├── ARCHITECTURE.md                # Architecture reference
├── CLAUDE.md                     # AI assistant guidance
├── LICENSE
├── Makefile                       # Convenience commands
├── plan.annapost.md               # Implementation plan
└── README.md
```

---

## DEVELOPMENT

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
```

### Linting and Formatting

```bash
# Run linter
ruff check .

# Format code
ruff format .

# Auto-fix lint issues
ruff check --fix .
```

### Makefile Commands

```bash
# Install dependencies
make install

# Run migrations
make migrate

# Run the application
make run

# Run tests
make test

# Run linter
make lint

# Clean build artifacts
make clean
```

### Database Operations

```bash
# Apply all migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "description of changes"

# Downgrade a migration
alembic downgrade -1

# Show migration history
alembic history
```

---

## ARCHITECTURE PRINCIPLES

### Design Constraints (DO NOT VIOLATE)

#### ❌ Never Do:
- Couple to Vend1r or any external producer internals
- Hardcode a single Instagram account
- Perform external HTTP calls while holding a SQLite write transaction
- Treat missing metrics as zero (NULL ≠ 0)
- Overwrite historical metric snapshots
- Silently retry permanent errors forever
- Physically delete operational history by default
- Add Redis/Celery/RabbitMQ without demonstrated need
- Duplicate Instagram API logic across runners

#### ✅ Always Do:
- Use the API as the integration boundary
- Keep runners independently executable
- Make all operations idempotent
- Preserve raw Instagram responses where useful
- Keep all posts account-specific
- Use append-only events for important actions
- Store historical metrics
- Support eventual reconciliation
- Design around Instagram API instability

### Key Patterns Implemented

1. **Idempotency:** Atomic claim pattern using conditional UPDATE with rowcount check
2. **Short Transactions:** No SQLite write transaction spans an HTTP call
3. **State Machine:** Explicit transition table prevents arbitrary state changes
4. **Event Sourcing:** Append-only event table for reconstructability
5. **Repository Pattern:** Thin query helpers separate from business logic
6. **Service Layer:** Business logic and state transitions centralized

---

## TESTING

### Test Coverage
The project includes comprehensive tests covering:
- **Unit Tests:** State machine, services, repositories
- **Integration Tests:** Database migrations, runner behavior
- **API Tests:** Endpoint contracts, validation
- **Runner Tests:** Idempotency, crash recovery, concurrency
- **UI Tests:** Admin dashboard rendering

### Test Strategy
- All Instagram HTTP calls are mocked using `respx`
- No real Instagram API calls in automated tests
- Tests use temporary SQLite databases
- Async tests supported via `pytest-asyncio`

---

## SECURITY

### Security Practices
- Access tokens are stored as references, never in plaintext
- Tokens are never exposed in API responses or logs
- Input validation for all external data (URLs, media sources)
- Structured logging without sensitive information
- Security headers on API responses

### Security Review Checklist
- [ ] Access tokens never appear in API responses
- [ ] Secrets live outside source control
- [ ] External URLs are validated before use
- [ ] No arbitrary filesystem access
- [ ] Error messages don't leak sensitive information
- [ ] Rate limiting on API endpoints (future)
- [ ] Security headers configured

---

## PERFORMANCE CONSIDERATIONS

### Current Performance Characteristics
- **API Response Time:** Fast (FastAPI + async SQLAlchemy)
- **Database Queries:** Optimized with proper indexing
- **Concurrent Processing:** SQLite WAL mode supports concurrent readers
- **Runner Throughput:** Configurable batch sizes

### Bottlenecks and Mitigations

| Bottleneck | Impact | Mitigation |
|-----------|--------|------------|
| SQLite single-writer lock | Bottleneck under heavy write load | WAL mode, short transactions |
| Network I/O | Primary latency source | Connection pooling, retry with backoff |
| Sequential Processing | Runners process items sequentially | Configurable batch sizes, parallel processing future |

---

## TROUBLESHOOTING

### Common Issues

#### No default account configured
- **Symptom:** API requests fail with no default account error
- **Solution:** Ensure at least one account has `is_default = true` and `enabled = true`
- **Check:** `python -m app.cli.main accounts list`

#### Lock stale after timeout
- **Symptom:** Runner appears stuck, posts not processing
- **Cause:** A runner crashed while holding a lock
- **Solution:** Wait for `LOCK_STALE_AFTER_SECONDS` (default 10 minutes) to expire, or manually clear lock

#### Database locked
- **Symptom:** Database locked errors
- **Cause:** Multiple processes accessing SQLite simultaneously
- **Solution:** Ensure WAL mode is enabled (default in AnnaPost), increase `busy_timeout` if needed

#### Instagram API error
- **Symptom:** Instagram-related errors in logs
- **Debug:** Check error type and message, verify access token validity, check rate limit status

#### `publish-file` rejects the account before creating a tunnel
- **Symptom:** `No enabled publishable account`
- **Cause:** The selected account lacks `instagram_user_id`, an `env:` token
  reference, the referenced environment variable, or `enabled = true`
- **Solution:** Repair the account through `/docs` or Admin, then rerun with
  `--account-id` or make it the enabled default

#### `publish-file` cannot create an ngrok tunnel
- **Symptom:** ngrok is unavailable, unauthenticated, or the 30-second startup
  wait expires
- **Solution:** Run `ngrok version` and `ngrok config check`, then verify that
  `http://127.0.0.1:4040/api/tunnels` becomes available while ngrok starts. No
  post is created until the CLI discovers an HTTPS tunnel for its own loopback
  origin.

#### A one-shot publish failed
- **Symptom:** JSON output has `"ok": false` and a failed post status
- **Behavior:** The temporary tunnel is closed and its pending job is canceled;
  it will not retry automatically
- **Solution:** Inspect the post/job/event history, correct the issue, then run
  a new `publish-file` command so Instagram receives a fresh reachable URL

#### Instagram returns `Media ID is not available`
- **Symptom:** The container ID is persisted, but the publish job fails with
  `Media ID is not available`.
- **Check:** Query the persisted container status before retrying. If it later
  reports `FINISHED`, explicitly retry the same post/job through the runner;
  the publisher reuses the existing `instagram_container_id` and starts a
  fresh temporary tunnel for durable local media.
- **Safety:** Do not create a second container until the remote state confirms
  that the original container cannot be published and the existing job is not
  already completed.

### Debug Mode
Enable debug mode for verbose logging:

```bash
DEBUG=true uvicorn app.main:app --reload
```

---

## DOCUMENTATION

### Core Documentation Files

| File | Purpose | Audience |
|------|---------|----------|
| `README.md` | Project overview, setup, usage | New developers, users |
| `ARCHITECTURE.md` | Detailed architecture reference | Developers, architects |
| `SECURITY.md` | Security boundaries and deployment practices | Operators, developers |
| `plan.annapost.md` | Implementation plan and specifications | Developers, contributors |
| `CLAUDE.md` | AI assistant guidance | AI tools, developers |
| `annapost-deep-code-review.md` | Comprehensive code review | Reviewers, maintainers |

### Phase Documentation
- `phases/01-prebuild.md` - Skeleton setup and tooling
- `phases/02-architecture.md` - Architecture decisions and contracts
- `phases/03-implementation.md` - Implementation details
- `phases/04-ui.md` - Admin UI implementation
- `phases/05-review.md` - Review and hardening checklist

---

## VERSION HISTORY

| Version | Date | Status | Notes |
|---------|------|--------|-------|
| 0.1.0 | 2026-08-11 | Phase 3 Complete | Implementation complete, Admin UI and Review pending |

---

## LICENSE

MIT License - see [LICENSE](LICENSE) file for details.

---

## GETTING HELP

### Documentation Links
- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed architecture reference
- [plan.annapost.md](plan.annapost.md) - Implementation plan
- [phases/](phases/) - Phase-specific documentation
- [annapost-deep-code-review.md](annapost-deep-code-review.md) - Comprehensive code review

### Support
For questions or issues, refer to the project documentation or open an issue in the repository.
