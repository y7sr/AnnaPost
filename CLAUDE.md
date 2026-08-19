# CLAUDE.md

**AI Assistant Guidance for AnnaPost Development**

This file provides guidance to AI coding assistants when working with code in this repository.

**Last Updated:** 2026-08-19
**Project Version:** 0.1.1
**Project Status:** Stabilized Phase 3 service with implemented admin UI

---

## Project Overview

AnnaPost is a standalone Instagram publishing and management system, built to be independent of Vend1r (or any other external producer). Vend1r may create/modify data through the API, but this project owns its own database, API, account config, publishing, sync, comments, deletion/reconciliation, metrics, and retry/operational state.

The full spec lives in `plan.annapost.md` (35 sections). The build is broken into phases in `phases/*.md`:

- `phases/01-prebuild.md` — skeleton (done)
- `phases/02-architecture.md` — full data model, state machine, contracts (done 2026-08-11)
- `phases/03-implementation.md` — services/API/runners (**COMPLETED 2026-08-11**)
- `phases/04-ui.md` — server-rendered `/admin` dashboard (in progress)
- `phases/05-review.md` — historical review plan; current stabilization is
  recorded in `docs/INDEX.md` and the root testing documentation.

**Current Status:** 151 tests, Ruff, formatting, durable-media isolation, and
an authenticated Instagram sync were verified on 2026-08-19. Historical code
reviews are not the current source of truth.

---

## Commands

### Setup
```bash
uv sync                                  # or: pip install -e ".[dev]"
make install
```

### Run the app
```bash
python -m app.main                       # dev server on :8000
uvicorn app.main:app --reload
make run
```

### Migrations
```bash
alembic upgrade head
alembic revision --autogenerate -m "description"
alembic downgrade -1
make migrate
```

### Runners
```bash
python -m app.runners.publish
python -m app.runners.bridge
python -m app.runners.sync
python -m app.runners.actions
```

`runner bridge` polls the configured Vend1r workspace, imports media into
AnnaPost-owned durable storage, and never publishes by itself. Configure
`VEND1R_BRIDGE_WORKSPACE_ID` and the shared `ANNAPOST_BRIDGE_TOKEN`; scheduling
is external to AnnaPost.

### CLI
```bash
python -m app.cli.main accounts list
python -m app.cli.main posts list
python -m app.cli.main runner publish

# Real Instagram write: local image via an ephemeral ngrok HTTPS URL.
# Requires a configured account and explicit --confirm.
python -m app.cli.main posts publish-file ./image.jpg --caption "Caption" --confirm
```

### Tests
```bash
pytest                                   # full suite
pytest --cov                           # with coverage
pytest tests/unit/test_foo.py::test_bar  # single test
make test
```

### Lint/Format
```bash
ruff check .
ruff format .
ruff check --fix .
make lint
```

---

## Architecture

**Core Principle:** DATABASE = desired state + internal history | INSTAGRAM = external state | RUNNERS = reconciliation between both

```
External Producer -> FastAPI -> Database -> Runners -> InstagramClient -> Instagram Graph API
```

**Layering:**
- `api/routes/` - thin HTTP layer (validation, status codes, no business logic)
- `admin/routes/` - template-based admin interfaces (Jinja2 + HTMX)
- `services/` - business logic, state transitions
- `repositories/` - query helpers, thin
- `db/models/` - SQLAlchemy ORM models
- `db/session/` - Connection management
- `instagram/` - InstagramClient, typed errors, metric normalization
- `runners/` - external entrypoints
- `cli/` - thin, reuses services
- `core/` - config, logging, shared utilities

### One-Shot Local Image Publishing

`posts publish-file` is the sole local-file convenience path. It stages exactly
one validated image through a loopback-only server and `ngrok`, persists a
normal URL-backed post, and calls
`app.runners.publish.run_job(job_id)` so unrelated pending work is untouched.
The tunnel dies after the attempt; failures must not be retried later against
that URL. Keep `--confirm` mandatory and never invoke it as a test or without
fresh approval for the exact image and caption. For durable/scheduled media,
use a durable HTTPS source rather than this temporary path.

---

## Key Design Patterns

### Post State Machine
- States: `draft, ready, scheduled, publishing, published, failed, delete_requested, deleted, canceled`
- Transition table in `app/services/post_state_machine.py` (56 unit tests)

### Idempotency
- Atomic claim pattern: conditional UPDATE + rowcount check
- Worker ID: `{hostname}:{pid}:{random_hex8}`
- Stale-lock timeout: 600s

### Metrics
- NULL = unavailable, 0 = Instagram reported zero
- `raw_metrics_json` preserves original payload

### Error Classification
- Transient: timeout, network, 429, 5xx → retry
- Permanent: auth, permission, validation → no retry

---

## Design Constraints

**DO NOT:**
- Couple to Vend1r internals
- Hardcode one Instagram account
- Hold SQLite write transactions during HTTP calls
- Treat NULL metrics as 0
- Duplicate Instagram API logic
- Add Redis/Celery without need

**DO:**
- Use API as integration boundary
- Keep runners independently executable
- Make operations idempotent
- Preserve raw Instagram responses
- Support eventual reconciliation

---

## Current Status

### Completed
- All Phase 1-3 tasks
- All architectural decisions implemented
- All API endpoints functional
- All runners working
- Comprehensive test coverage

### In Progress
- Admin UI dashboard (Phase 4)

### Not Started
- Product-directed admin UI expansion

---

## File Structure

```
app/
├── main.py
├── admin/      # Phase 4
├── api/
│   └── routes/
├── cli/
├── core/
├── db/
├── instagram/
├── repositories/
├── runners/
└── services/

tests/
├── unit/
├── api/
├── integration/
├── runners/
└── ui/
```

---

## Documentation

- `README.md` - Setup and usage
- `ARCHITECTURE.md` - Full architecture reference  
- `plan.annapost.md` - Implementation plan
- `phases/*.md` - Phase documentation
- `annapost-deep-code-review.md` - Comprehensive code review
- `docs/INDEX.md` - task routing for coding agents

---

*Updated 2026-08-12 for AnnaPost v0.1.0*
