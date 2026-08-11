"""SQLAlchemy model for Instagram posts."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
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
    from app.db.models.comment import InstagramComment
    from app.db.models.event import InstagramEvent
    from app.db.models.job import InstagramJob
    from app.db.models.metrics import InstagramPostMetric


class PostMediaType(enum.StrEnum):
    """Media type for Instagram posts."""

    IMAGE = "image"
    CAROUSEL = "carousel"
    REEL = "reel"


class PostMediaSourceType(enum.StrEnum):
    """Media source type for Instagram posts."""

    URL = "url"
    LOCAL_FILE = "local_file"
    OBJECT_STORAGE = "object_storage"


class PostStatus(enum.StrEnum):
    """Status of an Instagram post."""

    DRAFT = "draft"
    READY = "ready"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    DELETE_REQUESTED = "delete_requested"
    DELETED = "deleted"
    CANCELED = "canceled"


class InstagramPost(Base):
    """
    Central desired-state table for Instagram posts.

    Represents a post that should be (or has been) published to Instagram.
    """

    __tablename__ = "instagram_posts"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Account reference
    account_id: Mapped[int] = mapped_column(
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Media configuration
    media_type: Mapped[PostMediaType] = mapped_column(
        Enum(
            PostMediaType,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
    )
    media_source_type: Mapped[PostMediaSourceType] = mapped_column(
        Enum(
            PostMediaSourceType,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
    )
    media_source: Mapped[str] = mapped_column(String(2048), nullable=False)
    media_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)

    # Content
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_caption_last_known: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption_sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default="in_sync")

    # State management
    status: Mapped[PostStatus] = mapped_column(
        Enum(
            PostStatus,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
        default=PostStatus.DRAFT,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Instagram identifiers (populated after successful publishing)
    instagram_media_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    instagram_container_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    instagram_permalink: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Publication timestamps
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    soft_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delete_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Publishing attempt tracking
    publish_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_publish_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Synchronization tracking
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Idempotency
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    # Locking for idempotency (claim pattern)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    account: Mapped[InstagramAccount] = relationship(
        "InstagramAccount",
        back_populates="posts",
        foreign_keys=[account_id],
    )
    metrics: Mapped[list[InstagramPostMetric]] = relationship(
        "InstagramPostMetric",
        back_populates="post",
        foreign_keys="InstagramPostMetric.post_id",
        cascade="all, delete-orphan",
    )
    comments: Mapped[list[InstagramComment]] = relationship(
        "InstagramComment",
        back_populates="post",
        foreign_keys="InstagramComment.post_id",
        cascade="all, delete-orphan",
    )
    events: Mapped[list[InstagramEvent]] = relationship(
        "InstagramEvent",
        back_populates="post",
        foreign_keys="InstagramEvent.post_id",
        passive_deletes=True,
    )
    jobs: Mapped[list[InstagramJob]] = relationship(
        "InstagramJob",
        back_populates="post",
        foreign_keys="InstagramJob.post_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # Index on status for filtering posts by state
        Index("ix_instagram_posts_status", "status"),
        # Index on scheduled_at for finding due scheduled posts
        Index("ix_instagram_posts_scheduled_at", "scheduled_at"),
        # Index on next_sync_at for finding posts due for sync
        Index("ix_instagram_posts_next_sync_at", "next_sync_at"),
        # Index on account_id + status for account-specific queries
        Index("ix_instagram_posts_account_status", "account_id", "status"),
        # Index on locked_at for stale lock detection
        Index("ix_instagram_posts_locked_at", "locked_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<InstagramPost(id={self.id}, account_id={self.account_id}, "
            f"media_type={self.media_type.value}, status={self.status.value})>"
        )
