"""SQLAlchemy base model and metadata."""

from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


def utcnow() -> datetime:
    """Current UTC time as a naive datetime, matching the naive DATETIME columns used throughout the schema."""
    return datetime.now(UTC).replace(tzinfo=None)
