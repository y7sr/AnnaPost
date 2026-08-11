"""Pydantic contracts for Instagram post API payloads and responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.db.models.post import PostMediaSourceType, PostMediaType, PostStatus


class CarouselMediaItem(BaseModel):
    """One carousel child; the outer post owns the shared caption and account."""

    model_config = ConfigDict(extra="forbid")

    media_type: Literal[PostMediaType.IMAGE, PostMediaType.REEL]
    media_source_type: PostMediaSourceType
    media_source: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def validate_url_source(self) -> CarouselMediaItem:
        if self.media_source_type is PostMediaSourceType.URL:
            HttpUrl(self.media_source)
        return self


class CarouselMediaPayload(BaseModel):
    """Stored ``media_payload_json`` shape for a carousel post.

    ``items`` contains two to ten independently resolvable source objects.
    The Phase 3 publishing service resolves them through ``MediaResolver`` and
    passes only safe URLs to ``InstagramClient``.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[CarouselMediaItem] = Field(min_length=2, max_length=10)


class InstagramPostCreate(BaseModel):
    """External-producer creation contract.

    ``account_id`` is intentionally optional: Phase 3 resolves it to the one
    enabled default account. Producers cannot set lifecycle status or remote
    Instagram identifiers through this endpoint.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "caption": "Example post caption",
                "media_type": "image",
                "media_source_type": "url",
                "media_source": "https://example.com/image.jpg",
            }
        },
    )

    account_id: int | None = Field(None, ge=1)
    media_type: PostMediaType
    media_source_type: PostMediaSourceType
    media_source: str = Field(min_length=1, max_length=2048)
    media_payload_json: dict[str, Any] | None = None
    caption: str | None = None
    scheduled_at: datetime | None = None
    idempotency_key: str | None = Field(None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_media_payload(self) -> InstagramPostCreate:
        if self.media_source_type is PostMediaSourceType.URL:
            HttpUrl(self.media_source)
        if self.media_type is PostMediaType.CAROUSEL:
            if self.media_payload_json is None:
                raise ValueError("Carousel posts require media_payload_json.items")
            self.media_payload_json = CarouselMediaPayload.model_validate(
                self.media_payload_json
            ).model_dump(mode="json")
        elif self.media_payload_json is not None:
            raise ValueError("media_payload_json is currently reserved for carousel posts")
        return self


class InstagramPostUpdate(BaseModel):
    """Editable desired-state fields; lifecycle changes use dedicated services."""

    model_config = ConfigDict(extra="forbid")

    media_type: PostMediaType | None = None
    media_source_type: PostMediaSourceType | None = None
    media_source: str | None = Field(None, min_length=1, max_length=2048)
    media_payload_json: dict[str, Any] | None = None
    caption: str | None = None


class InstagramPostBase(BaseModel):
    """Fields common to the persisted post representation."""

    account_id: int
    media_type: PostMediaType
    media_source_type: PostMediaSourceType
    media_source: str
    media_payload_json: dict[str, Any] | None
    caption: str | None
    remote_caption_last_known: str | None = None
    caption_sync_status: str = "in_sync"
    status: PostStatus
    scheduled_at: datetime | None
    idempotency_key: str | None


class InstagramPostResponse(InstagramPostBase):
    """Post returned by read and future write endpoints."""

    id: int
    instagram_media_id: str | None = None
    instagram_container_id: str | None = None
    instagram_permalink: str | None = None
    published_at: datetime | None = None
    deleted_at: datetime | None = None
    soft_deleted: bool
    delete_requested_at: datetime | None = None
    publish_attempt_count: int
    last_publish_attempt_at: datetime | None = None
    last_synced_at: datetime | None = None
    next_sync_at: datetime | None = None
    locked_at: datetime | None = None
    locked_by: str | None = None
    created_at: datetime
    updated_at: datetime
    last_error: str | None = None

    model_config = ConfigDict(from_attributes=True)


class InstagramPostListResponse(BaseModel):
    """List envelope for posts."""

    posts: list[InstagramPostResponse]
    count: int


class InstagramPostSchedule(BaseModel):
    """Request a future publication time."""

    model_config = ConfigDict(extra="forbid")

    scheduled_at: datetime


class InstagramPostPublish(BaseModel):
    """Request immediate publication; actual execution remains asynchronous."""

    model_config = ConfigDict(extra="forbid")

    idempotency_key: str | None = Field(None, min_length=1, max_length=255)
