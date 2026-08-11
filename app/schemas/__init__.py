"""Pydantic schemas for AnnaPost."""

from app.schemas.account import (
    InstagramAccountBase,
    InstagramAccountCreate,
    InstagramAccountListResponse,
    InstagramAccountResponse,
    InstagramAccountUpdate,
)
from app.schemas.comment import (
    CommentCreateRequest,
    InstagramCommentBase,
    InstagramCommentCreate,
    InstagramCommentListResponse,
    InstagramCommentResponse,
    ReplyCreateRequest,
)
from app.schemas.event import (
    InstagramEventBase,
    InstagramEventCreate,
    InstagramEventListResponse,
    InstagramEventResponse,
)
from app.schemas.job import (
    InstagramJobBase,
    InstagramJobCreate,
    InstagramJobListResponse,
    InstagramJobResponse,
    InstagramJobUpdate,
)
from app.schemas.metrics import (
    InstagramPostMetricBase,
    InstagramPostMetricCreate,
    InstagramPostMetricListResponse,
    InstagramPostMetricResponse,
    MetricSnapshotCreate,
)
from app.schemas.option import (
    GlobalOptionBase,
    GlobalOptionCreate,
    GlobalOptionListResponse,
    GlobalOptionResponse,
    GlobalOptionUpdate,
)
from app.schemas.post import (
    CarouselMediaItem,
    CarouselMediaPayload,
    InstagramPostBase,
    InstagramPostCreate,
    InstagramPostListResponse,
    InstagramPostPublish,
    InstagramPostResponse,
    InstagramPostSchedule,
    InstagramPostUpdate,
)

__all__ = [
    # Account schemas
    "InstagramAccountBase",
    "InstagramAccountCreate",
    "InstagramAccountListResponse",
    "InstagramAccountResponse",
    "InstagramAccountUpdate",
    # Comment schemas
    "CommentCreateRequest",
    "InstagramCommentBase",
    "InstagramCommentCreate",
    "InstagramCommentListResponse",
    "InstagramCommentResponse",
    "ReplyCreateRequest",
    # Event schemas
    "InstagramEventBase",
    "InstagramEventCreate",
    "InstagramEventListResponse",
    "InstagramEventResponse",
    # Job schemas
    "InstagramJobBase",
    "InstagramJobCreate",
    "InstagramJobListResponse",
    "InstagramJobResponse",
    "InstagramJobUpdate",
    # Metric schemas
    "InstagramPostMetricBase",
    "InstagramPostMetricCreate",
    "InstagramPostMetricListResponse",
    "InstagramPostMetricResponse",
    "MetricSnapshotCreate",
    # Option schemas
    "GlobalOptionBase",
    "GlobalOptionCreate",
    "GlobalOptionListResponse",
    "GlobalOptionResponse",
    "GlobalOptionUpdate",
    # Post schemas
    "CarouselMediaItem",
    "CarouselMediaPayload",
    "InstagramPostBase",
    "InstagramPostCreate",
    "InstagramPostListResponse",
    "InstagramPostPublish",
    "InstagramPostResponse",
    "InstagramPostSchedule",
    "InstagramPostUpdate",
]
