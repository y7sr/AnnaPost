"""Retry classification and backoff contract for queued Instagram actions."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.instagram.errors import InstagramError, InstagramRateLimitError
from app.services.options import get_option_value

# Stored as the fallback for the mutable ``global_options.retry_backoff``
# setting. Values are seconds and represent attempts 1, 2, 3, and 4+.
DEFAULT_RETRY_BACKOFF_SECONDS = (60, 300, 900, 3600)


def is_retryable(error: Exception) -> bool:
    """Return whether a failed job may be retried automatically."""
    return isinstance(error, InstagramError) and error.retryable


def retry_delay_seconds(
    error: Exception,
    *,
    attempt: int,
    backoff_seconds: tuple[int, ...] = DEFAULT_RETRY_BACKOFF_SECONDS,
) -> int | None:
    """Choose a bounded delay, respecting an explicit rate-limit response."""
    if not is_retryable(error):
        return None
    if isinstance(error, InstagramRateLimitError) and error.retry_after_seconds:
        return error.retry_after_seconds
    if attempt < 1:
        raise ValueError("attempt must be at least 1")
    return backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]


async def configured_retry_delay_seconds(
    session: AsyncSession, error: Exception, *, attempt: int
) -> int | None:
    """Apply the mutable DB backoff only when it is a safe integer sequence."""
    raw = await get_option_value(session, "retry_backoff")
    values = (
        tuple(item for item in raw if isinstance(item, int) and item > 0)
        if isinstance(raw, list)
        else DEFAULT_RETRY_BACKOFF_SECONDS
    )
    return retry_delay_seconds(
        error, attempt=attempt, backoff_seconds=values or DEFAULT_RETRY_BACKOFF_SECONDS
    )
