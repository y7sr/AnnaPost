"""SQLAlchemy model for Instagram comments."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow

if TYPE_CHECKING:
    from app.db.models.account import InstagramAccount
    from app.db.models.post import InstagramPost


class InstagramComment(Base):
    """
    Stores remote Instagram comments locally.

    Represents comments on Instagram posts, fetched via the API.
    Comment synchronization must update existing rows instead of creating duplicates.
    """

    __tablename__ = "instagram_comments"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Account and post references
    account_id: Mapped[int] = mapped_column(
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    post_id: Mapped[int] = mapped_column(
        ForeignKey("instagram_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Instagram identifiers
    instagram_comment_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    parent_instagram_comment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Author information
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    instagram_user_id_if_available: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Comment content
    text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at_remote: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    # Engagement
    like_count_if_available: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )

    # Flags
    is_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_deleted_remote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Raw payload preservation
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)

    # Relationships
    account: Mapped[InstagramAccount] = relationship(
        "InstagramAccount",
        back_populates="comments",
        foreign_keys=[account_id],
    )
    post: Mapped[InstagramPost] = relationship(
        "InstagramPost",
        back_populates="comments",
        foreign_keys=[post_id],
    )
    # Self-referential by Instagram comment ID, not a DB foreign key (a reply's
    # parent may not be synced locally yet), so the join is spelled out
    # explicitly and the relationship is read-only.
    replies: Mapped[list[InstagramComment]] = relationship(
        "InstagramComment",
        primaryjoin=(
            "foreign(InstagramComment.parent_instagram_comment_id) "
            "== InstagramComment.instagram_comment_id"
        ),
        viewonly=True,
    )

    __table_args__ = (
        # Unique constraint on instagram_comment_id
        Index("ix_instagram_comments_instagram_id", "instagram_comment_id", unique=True),
        # Index on post_id for querying comments by post
        Index("ix_instagram_comments_post", "post_id"),
        # Index on account_id + post_id for account-specific queries
        Index("ix_instagram_comments_account_post", "account_id", "post_id"),
        # Index on parent for finding replies
        Index("ix_instagram_comments_parent", "parent_instagram_comment_id"),
        # Index on remote deletion flag
        Index("ix_instagram_comments_deleted", "is_deleted_remote"),
    )

    def __repr__(self) -> str:
        return (
            f"<InstagramComment(id={self.id}, instagram_comment_id={self.instagram_comment_id!r}, "
            f"post_id={self.post_id}, username={self.username!r})>"
        )
