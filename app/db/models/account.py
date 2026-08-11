"""SQLAlchemy model for Instagram accounts."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow

if TYPE_CHECKING:
    from app.db.models.comment import InstagramComment
    from app.db.models.event import InstagramEvent
    from app.db.models.post import InstagramPost


class InstagramAccount(Base):
    """
    Instagram account configuration.

    Represents a configured Instagram account that can be used for publishing.
    Exactly one account may be marked as default (is_default=True).
    """

    __tablename__ = "instagram_accounts"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Account identification
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    instagram_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Default account flag - exactly one row may have is_default=True
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Authentication - token reference, not plaintext
    access_token_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Operational timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    last_successful_api_call_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    posts: Mapped[list[InstagramPost]] = relationship(
        "InstagramPost",
        back_populates="account",
        foreign_keys="InstagramPost.account_id",
        cascade="all, delete-orphan",
    )
    comments: Mapped[list[InstagramComment]] = relationship(
        "InstagramComment",
        back_populates="account",
        foreign_keys="InstagramComment.account_id",
        cascade="all, delete-orphan",
    )
    events: Mapped[list[InstagramEvent]] = relationship(
        "InstagramEvent",
        back_populates="account",
        foreign_keys="InstagramEvent.account_id",
        passive_deletes=True,
    )

    __table_args__ = (
        # Partial unique index: only one account may have is_default=True.
        # SQLite supports partial (WHERE-qualified) unique indexes; enforced here
        # at the DB level rather than app-level. See ARCHITECTURE.md decision log.
        Index(
            "ux_instagram_accounts_is_default",
            "is_default",
            unique=True,
            sqlite_where=text("is_default = 1"),
        ),
    )

    def __repr__(self) -> str:
        return f"<InstagramAccount(id={self.id}, name={self.name!r}, is_default={self.is_default})>"
