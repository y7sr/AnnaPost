"""SQLAlchemy model for global options."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class GlobalOption(Base):
    """
    Simple configuration table for mutable application settings.

    Stores key-value pairs where the value can be any JSON-serializable data.
    No secrets should be stored here unless specifically required.
    """

    __tablename__ = "global_options"

    # Key is the primary key - each option has a unique key
    key: Mapped[str] = mapped_column(String(255), primary_key=True)

    # Value stored as JSON to support various data types
    value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSON, nullable=True, default=None
    )

    # Timestamp for when the option was last updated
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        # No additional indexes needed - key is already the primary key
    )

    def __repr__(self) -> str:
        return f"<GlobalOption(key={self.key!r}, value_json={self.value_json!r})>"
