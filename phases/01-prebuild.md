# Phase 1 — Prebuild (Simple)

Reference: `plan.annapost.md`, section 33 "Phase 1 — Skeleton".

## Goal

A working, empty skeleton. No business logic, no tables beyond Alembic's own bookkeeping, no Instagram code. Anyone can clone the repo and get `GET /health` → 200.

Difficulty: **simple** — mechanical scaffolding. The only decisions here are already prescribed by section 26 (repository structure) and section 1 (tech stack); there's no architecture to get wrong yet.

## Tasks

### 1. Repo & tooling
- `git init`, `.gitignore` (`.venv`, `__pycache__`, `*.db`, `.env`, `.pytest_cache`, `htmlcov`)
- `pyproject.toml` with Python 3.12+ and the dependencies from section 1: `fastapi`, `pydantic>=2`, `sqlalchemy>=2`, `aiosqlite`, `alembic`, `httpx`, `python-dotenv`; dev deps: `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`, `ruff`
- `ruff` config (lint + format), no other linters/formatters
- No pre-commit, no Docker, no Node toolchain — nothing not in section 1

### 2. App skeleton (section 26 structure)
Create the full package layout as empty modules, matching section 26 exactly:
```text
app/main.py
app/api/routes/{accounts,posts,comments,metrics,jobs,events,options}.py
app/core/{config.py,logging.py}
app/db/{base.py,session.py}, app/db/models/
app/schemas/{account,post,comment,metrics,job,event}.py
app/repositories/{accounts,posts,comments,jobs,metrics}.py
app/services/{accounts,posts,publishing,sync,actions,comments,reconciliation,media}.py
app/instagram/{client.py,errors.py,schemas.py,metrics.py}
app/runners/{publish.py,sync.py,actions.py}
app/cli/main.py
tests/{unit,integration,api,runners}
alembic/
```
- `app/main.py`: `FastAPI()` instance, includes routers (empty routers are fine), one real route: `GET /health` → `{"status": "ok"}`

### 3. Configuration (`core/config.py`)
- Pydantic `Settings` (via `pydantic-settings` or `BaseSettings` if bundled) loading from `.env` via `python-dotenv`
- Fields needed even at this stage: `database_url`, `log_level`; leave placeholders (commented) for `ig_graph_api_version` etc. — those get filled in Phase 2
- `.env.example` checked in; real `.env` gitignored

### 4. Logging (`core/logging.py`)
- Basic stdlib `logging` (or `structlog` if adopted per section 1's optional list) configured once at startup
- No token-redaction logic needed yet (nothing logs tokens yet) — full audit happens in Phase 5

### 5. Database bootstrap (`db/base.py`, `db/session.py`)
- SQLAlchemy 2.x async engine (`aiosqlite`) + async session factory
- On connect: `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=...` (section 27) — wire this now even though there are no tables yet, so it's never forgotten later
- Empty `declarative_base()` / `DeclarativeBase` subclass

### 6. Alembic
- `alembic init alembic`, `env.py` wired to `Settings.database_url` and the async engine, `target_metadata` pointed at the (currently empty) `Base.metadata`
- One baseline migration that creates nothing (or only Alembic's version table) — proves the migration pipeline works end to end
- No use of `Base.metadata.create_all()` anywhere (section 28 forbids it as the migration strategy)

### 7. Test infrastructure
- `pyproject.toml` `[tool.pytest.ini_options]`: `asyncio_mode = "auto"`
- `tests/conftest.py`: temp SQLite DB fixture (file-based tmp path, not the dev DB), async test client using `httpx.AsyncClient(transport=ASGITransport(app=app))`
- `tests/unit/`, `tests/integration/`, `tests/api/`, `tests/runners/` each get an `__init__.py` (or are picked up via rootdir config) and one smoke test
- `tests/api/test_health.py`: `GET /health` returns 200 and the expected body

### 8. Local dev convenience (optional, keep trivial)
- A short `README.md` or `Makefile` with `run`, `test`, `lint`, `migrate` targets — only if it stays a few lines; skip anything that needs its own maintenance

## Deliverables
- `uvicorn app.main:app --reload` boots with no errors
- `pytest` passes (health test only)
- `ruff check .` passes
- `alembic upgrade head` runs cleanly on a fresh SQLite file

## Definition of Done
Fresh clone → install deps → copy `.env.example` to `.env` → `alembic upgrade head` → `uvicorn app.main:app` → `curl localhost:8000/health` → `200 {"status": "ok"}`. No business tables, no Instagram code, no runner logic exist yet — that's expected and correct for this phase.

Next: [02-architecture.md](02-architecture.md)
