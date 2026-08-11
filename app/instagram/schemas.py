"""Typed payloads crossing the Instagram client boundary.

These are deliberately Graph-API-version-neutral.  The client implementation
added in Phase 3 will translate between these contracts and HTTP payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InstagramContainer(BaseModel):
    """A created media container awaiting publication."""

    id: str = Field(min_length=1)


class InstagramPublishedMedia(BaseModel):
    """The result returned after publishing a container."""

    id: str = Field(min_length=1)


class InstagramMedia(BaseModel):
    """Normalized representation of one remote media object."""

    id: str = Field(min_length=1)
    permalink: str | None = None
    caption: str | None = None
    timestamp: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class InstagramCarouselItem(BaseModel):
    """An already-resolved carousel child supplied to the client."""

    model_config = ConfigDict(extra="forbid")

    media_type: str = Field(pattern="^(image|reel)$")
    media_url: str = Field(min_length=1, max_length=2048)


class InstagramRemoteComment(BaseModel):
    """A remote comment returned by Instagram."""

    id: str = Field(min_length=1)
    text: str | None = None
    username: str | None = None
    timestamp: datetime | None = None
    parent_id: str | None = None
    like_count: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class InstagramCommentsPage(BaseModel):
    """One page of comments; pagination is intentionally opaque to services."""

    comments: list[InstagramRemoteComment] = Field(default_factory=list)
    next_cursor: str | None = None


class InstagramCreatedComment(BaseModel):
    """Identifier returned for a newly created comment or reply."""

    id: str = Field(min_length=1)
