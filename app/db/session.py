"""Database session management."""

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# SQLite PRAGMA settings, applied to every physical connection.  These need
# driver-level execution: AsyncConnection.execute() accepts SQLAlchemy clauses,
# not raw strings, and foreign_keys is connection-local.
SQLITE_PRAGMAS = (
    "PRAGMA foreign_keys=ON",
    "PRAGMA journal_mode=WAL",
    "PRAGMA busy_timeout=5000",
)

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={
        "check_same_thread": False,
    },
)


def apply_sqlite_pragmas(dbapi_connection: object) -> None:
    """Apply the required per-connection SQLite configuration."""
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        for pragma in SQLITE_PRAGMAS:
            cursor.execute(pragma)
    finally:
        cursor.close()


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection: object, _connection_record: object) -> None:
        """Set SQLite safety pragmas as each DBAPI connection is opened."""
        apply_sqlite_pragmas(dbapi_connection)


# Async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides a database session."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Open and validate the configured database connection.

    Schema creation remains Alembic-only.  Opening a connection also proves
    the connection lifecycle has applied the SQLite pragmas above.
    """
    async with engine.begin() as conn:
        await conn.exec_driver_sql("SELECT 1")
