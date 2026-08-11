"""SQLAlchemy model for Instagram jobs."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
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
    from app.db.models.post import InstagramPost


class JobType(enum.StrEnum):
    """Initial job types supported by the Phase 2 queue contract.

    New job types require an explicit schema/migration change.  Keeping future
    operations out of this enum prevents a runner from accepting work it does
    not yet know how to execute.
    """

    PUBLISH = "publish"
    DELETE_POST = "delete_post"
    CREATE_COMMENT = "create_comment"
    REPLY_COMMENT = "reply_comment"


class JobStatus(enum.StrEnum):
    """Status of a job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class InstagramJob(Base):
    """
    Lightweight internal job table for asynchronous desired actions.

    Jobs are idempotent where practical. SQLite is the queue.
    """

    __tablename__ = "instagram_jobs"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Job type
    job_type: Mapped[JobType] = mapped_column(
        Enum(
            JobType,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=False,
        index=True,
    )

    # References (nullable depending on job type)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("instagram_accounts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    post_id: Mapped[int | None] = mapped_column(
        ForeignKey("instagram_posts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    comment_id: Mapped[int | None] = mapped_column(
        ForeignKey("instagram_comments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Job payload (validated per job_type via Pydantic models)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)

    # State
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=False,
        default=JobStatus.PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Scheduling
    run_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Locking (claim pattern - mirrors post claiming)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Error tracking
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    account: Mapped[InstagramAccount | None] = relationship(
        "InstagramAccount",
        foreign_keys=[account_id],
    )
    post: Mapped[InstagramPost | None] = relationship(
        "InstagramPost",
        back_populates="jobs",
        foreign_keys=[post_id],
    )
    comment: Mapped[InstagramComment | None] = relationship(
        "InstagramComment",
        foreign_keys=[comment_id],
    )
    events: Mapped[list[InstagramEvent]] = relationship(
        "InstagramEvent",
        back_populates="job",
        foreign_keys="InstagramEvent.job_id",
        passive_deletes=True,
    )

    __table_args__ = (
        # Index on status + run_after for finding jobs ready to run
        Index("ix_instagram_jobs_status_run_after", "status", "run_after"),
        # Index on locked_at for stale lock detection
        Index("ix_instagram_jobs_locked_at", "locked_at"),
        # Index on created_at for ordering
        Index("ix_instagram_jobs_created", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<InstagramJob(id={self.id}, job_type={self.job_type.value}, "
            f"status={self.status.value}, post_id={self.post_id})>"
        )
