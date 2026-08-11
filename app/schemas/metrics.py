"""Pydantic schemas for Instagram post metrics."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InstagramPostMetricBase(BaseModel):
    """Base schema for InstagramPostMetric with common fields."""

    post_id: int = Field(..., description="ID of the associated post")
    captured_at: datetime = Field(..., description="When the metric snapshot was captured")

    # View/Reach metrics (nullable - NULL means unavailable)
    views: int | None = Field(None, description="Number of views (NULL = unavailable)")
    reach: int | None = Field(None, description="Reach count (NULL = unavailable)")
    plays: int | None = Field(None, description="Number of plays (NULL = unavailable)")

    # Watch time metrics (nullable - NULL means unavailable)
    avg_watch_time_ms: int | None = Field(
        None, description="Average watch time in ms (NULL = unavailable)"
    )
    total_watch_time_ms: int | None = Field(
        None, description="Total watch time in ms (NULL = unavailable)"
    )

    # Engagement metrics (nullable - NULL means unavailable)
    likes: int | None = Field(None, description="Number of likes (NULL = unavailable)")
    comments: int | None = Field(None, description="Number of comments (NULL = unavailable)")
    saved: int | None = Field(None, description="Number of saves (NULL = unavailable)")
    shares: int | None = Field(None, description="Number of shares (NULL = unavailable)")
    total_interactions: int | None = Field(
        None, description="Total interactions (NULL = unavailable)"
    )

    # Profile activity metrics (nullable - NULL means unavailable)
    profile_activity: int | None = Field(
        None, description="Profile activity count (NULL = unavailable)"
    )
    follows: int | None = Field(None, description="Number of follows (NULL = unavailable)")

    # Raw payload preservation
    raw_metrics_json: dict | None = Field(None, description="Raw Instagram API response payload")


class InstagramPostMetricCreate(InstagramPostMetricBase):
    """Schema for creating a new metric snapshot."""

    pass


class InstagramPostMetricResponse(InstagramPostMetricBase):
    """Schema for InstagramPostMetric responses with all fields."""

    id: int = Field(..., description="Metric snapshot ID")

    model_config = ConfigDict(from_attributes=True)


class InstagramPostMetricListResponse(BaseModel):
    """Schema for listing metrics for a post."""

    metrics: list[InstagramPostMetricResponse] = Field(..., description="List of metric snapshots")
    count: int = Field(..., description="Total number of snapshots")


class MetricSnapshotCreate(BaseModel):
    """Schema for requesting metric snapshot creation."""

    pass
