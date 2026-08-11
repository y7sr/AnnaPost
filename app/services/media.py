"""Media resolution contracts for publishable Instagram URLs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import urlparse

from app.db.models.post import PostMediaSourceType


class MediaResolutionError(ValueError):
    """Raised when a configured media source cannot safely be resolved."""


class MediaResolver(ABC):
    """Resolve a stored source into the URL Instagram can fetch.

    Implementations must not expose arbitrary local files. Phase 2 ships only
    the URL resolver; object-storage and local-file resolvers are Phase 3+
    additions behind this same interface.
    """

    @abstractmethod
    async def resolve(
        self,
        *,
        source_type: PostMediaSourceType,
        source: str,
    ) -> str:
        """Return an Instagram-fetchable URL or raise ``MediaResolutionError``."""


class UrlMediaResolver(MediaResolver):
    """v1 resolver for a pre-existing public HTTPS/HTTP URL."""

    async def resolve(
        self,
        *,
        source_type: PostMediaSourceType,
        source: str,
    ) -> str:
        if source_type is not PostMediaSourceType.URL:
            raise MediaResolutionError(
                f"Media source type {source_type.value!r} has no resolver yet"
            )

        parsed = urlparse(source)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise MediaResolutionError("Media URL must be an absolute HTTP(S) URL")
        return source
