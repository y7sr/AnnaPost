"""SQLAlchemy model for Instagram events."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow

if TYPE_CHECKING:
    from app.db.models.account import InstagramAccount
    from app.db.models.job import InstagramJob
    from app.db.models.post import InstagramPost


class EventType(enum.StrEnum):
    """Type of event that can be recorded."""

    # Post events
    POST_CREATED = "post_created"
    POST_UPDATED = "post_updated"
    POST_SCHEDULED = "post_scheduled"

    # Publishing events
    PUBLISH_STARTED = "publish_started"
    PUBLISH_SUCCEEDED = "publish_succeeded"
    PUBLISH_FAILED = "publish_failed"

    # Sync events
    SYNC_STARTED = "sync_started"
    SYNC_SUCCEEDED = "sync_succeeded"
    SYNC_FAILED = "sync_failed"

    # Metric events
    METRIC_SNAPSHOT_CREATED = "metric_snapshot_created"

    # Deletion events
    DELETE_REQUESTED = "delete_requested"
    DELETE_STARTED = "delete_started"
    DELETE_SUCCEEDED = "delete_succeeded"
    DELETE_FAILED = "delete_failed"

    # Comment events
    COMMENT_RECEIVED = "comment_received"
    COMMENT_QUEUED = "comment_queued"
    COMMENT_SENT = "comment_sent"
    COMMENT_FAILED = "comment_failed"


class InstagramEvent(Base):
    """
    Append-only operational/audit log.

    Records important actions and state changes for reconstructability.
    Goal: What happened? When? To which post/account? What did Instagram return?
    """

    __tablename__ = "instagram_events"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # References (nullable depending on event)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("instagram_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    post_id: Mapped[int | None] = mapped_column(
        ForeignKey("instagram_posts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("instagram_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Event type and payload
    event_type: Mapped[EventType] = mapped_column(
        Enum(
            EventType,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
        index=True,
    )
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )

    # Relationships
    account: Mapped[InstagramAccount | None] = relationship(
        "InstagramAccount",
        back_populates="events",
        foreign_keys=[account_id],
    )
    post: Mapped[InstagramPost | None] = relationship(
        "InstagramPost",
        back_populates="events",
        foreign_keys=[post_id],
    )
    job: Mapped[InstagramJob | None] = relationship(
        "InstagramJob",
        back_populates="events",
        foreign_keys=[job_id],
    )

    __table_args__ = (
        # Index on account_id + created_at for account-specific event queries
        Index("ix_instagram_events_account_created", "account_id", "created_at"),
        # Index on post_id + created_at for post-specific event queries
        Index("ix_instagram_events_post_created", "post_id", "created_at"),
        # Index on job_id + created_at for job-specific event queries
        Index("ix_instagram_events_job_created", "job_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<InstagramEvent(id={self.id}, event_type={self.event_type.value}, "
            f"account_id={self.account_id}, post_id={self.post_id}, job_id={self.job_id})>"
        )
