"""Pytest configuration and fixtures."""

import os
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from app.core.config import settings

REPO_ROOT = Path(__file__).resolve().parents[1]

# SQLAlchemy async engine for tests
# Each test gets its own temporary database file


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Create a temporary database file for testing."""
    # Create a temporary directory for test databases
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"
    yield db_path
    # Cleanup
    if db_path.exists():
        os.unlink(db_path)
    if temp_dir.exists():
        os.rmdir(temp_dir)


@pytest.fixture(autouse=True)
async def setup_test_db(
    temp_db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[None, None]:
    """Create each test database through the real Alembic migration path."""
    for name in ("TOKEN", "TOKEN_1", "TOKEN_2", "SECRET_TOKEN"):
        monkeypatch.setenv(name, f"test-{name.lower()}")
    db_url = f"sqlite+aiosqlite:///{temp_db_path}"
    monkeypatch.setattr(settings, "database_url", db_url)
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.upgrade(config, "head")

    yield


@pytest.fixture
async def db_session(temp_db_path: Path, setup_test_db: None) -> AsyncGenerator[AsyncSession, None]:
    """Provide an AsyncSession against the per-test database (tables already created)."""
    db_url = f"sqlite+aiosqlite:///{temp_db_path}"
    engine = create_async_engine(db_url, echo=False, connect_args={"check_same_thread": False})
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def test_app() -> Any:
    """Import and return the FastAPI app for testing."""
    from app.main import app

    return app


@pytest.fixture
async def async_client(
    test_app: Any, db_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTPX client for testing the app."""
    from app.db.session import get_db

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_db
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    test_app.dependency_overrides.clear()
