"""Pytest configuration and fixtures."""

import shutil
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


@pytest.fixture
def mock_post_media_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate post creation tests from external media acquisition."""
    from app.services import posts

    async def fake_import_media(*, source_type: object, source: str) -> str:
        del source_type, source
        from app.services.media_storage import storage_path

        key = "test-media.jpg"
        storage_path(key).write_bytes(b"test media")
        return key

    monkeypatch.setattr(posts, "import_media", fake_import_media)


# SQLAlchemy async engine for tests
# Each test gets its own temporary database file


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Create a temporary database file for testing."""
    # Create a temporary directory for test databases
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"
    yield db_path
    # Cleanup the database and test-only durable-media directory together.
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
async def setup_test_db(
    temp_db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[None, None]:
    """Create each test database through the real Alembic migration path."""
    for name in ("TOKEN", "TOKEN_1", "TOKEN_2", "SECRET_TOKEN"):
        monkeypatch.setenv(name, f"test-{name.lower()}")
    db_url = f"sqlite+aiosqlite:///{temp_db_path}"
    monkeypatch.setattr(settings, "database_url", db_url)
    monkeypatch.setattr(settings, "media_storage_dir", temp_db_path.parent / "media")
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
    test_app: Any, db_session: AsyncSession, mock_post_media_import: None
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
