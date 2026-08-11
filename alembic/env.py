"""Alembic environment configuration for async SQLAlchemy.

This file is configured to work with async SQLAlchemy (aiosqlite) by
using a synchronous SQLite engine for Alembic operations.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import settings
from app.db.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use the app's Base.metadata as the target
target_metadata = Base.metadata

# Override the database URL from settings
# We use a sync engine for Alembic since it doesn't support async natively
# Convert aiosqlite URL to sqlite URL
# settings.database_url is like: sqlite+aiosqlite:///./data/annapost.db
# We need: sqlite:///./data/annapost.db
sync_database_url = settings.database_url.replace("aiosqlite", "sqlite").replace(
    "sqlite+sqlite", "sqlite"
)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = sync_database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Run migrations on a connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Create a synchronous SQLite engine for Alembic
    # Alembic does not support async engines natively
    connectable = create_engine(
        sync_database_url,
        poolclass=pool.NullPool,
        connect_args={
            "check_same_thread": False,
        },
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
