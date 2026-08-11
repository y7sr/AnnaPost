"""SQLAlchemy model for Instagram post metrics."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, utcnow

if TYPE_CHECKING:
    from app.db.models.post import InstagramPost


class InstagramPostMetric(Base):
    """
    Historical metric snapshots for Instagram posts.

    Stores point-in-time metrics for a post. Each row is a snapshot,
    never overwritten. NULL means "unavailable", never 0.
    """

    __tablename__ = "instagram_post_metrics"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Post reference
    post_id: Mapped[int] = mapped_column(
        ForeignKey("instagram_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Snapshot timestamp
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    # View/Reach metrics (nullable - NULL means unavailable)
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reach: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plays: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Watch time metrics (nullable - NULL means unavailable)
    avg_watch_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_watch_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Engagement metrics (nullable - NULL means unavailable)
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    saved: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shares: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_interactions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Profile activity metrics (nullable - NULL means unavailable)
    profile_activity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    follows: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Raw payload preservation
    raw_metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)

    # Relationships
    post: Mapped[InstagramPost] = relationship(
        "InstagramPost",
        back_populates="metrics",
        foreign_keys=[post_id],
    )

    __table_args__ = (
        # Index on post_id + captured_at for querying metrics history
        Index("ix_instagram_post_metrics_post_captured", "post_id", "captured_at"),
        # Index on captured_at for time-based queries
        Index("ix_instagram_post_metrics_captured", "captured_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<InstagramPostMetric(id={self.id}, post_id={self.post_id}, "
            f"captured_at={self.captured_at})>"
        )
