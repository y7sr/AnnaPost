"""Typed failures at the Instagram Graph API boundary.

Phase 3 services use these classes to decide whether a job may be retried.
They intentionally carry only safe diagnostic metadata; access tokens and raw
response bodies never belong in an exception message.
"""

from __future__ import annotations


class InstagramError(Exception):
    """Base error raised by :class:`app.instagram.client.InstagramClient`."""

    retryable = False

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class InstagramTransientError(InstagramError):
    """Timeout, network, or server-side error that may be retried."""

    retryable = True


class InstagramRateLimitError(InstagramTransientError):
    """Rate limit; retry after the supplied delay or normal backoff."""


class InstagramAuthenticationError(InstagramError):
    """Invalid or expired account credentials; requires operator action."""


class InstagramPermissionError(InstagramError):
    """Missing Graph API permission or account capability; permanent."""


class InstagramValidationError(InstagramError):
    """Invalid media or request payload; permanent for the current action."""


class InstagramNotFoundError(InstagramError):
    """Remote object does not exist.

    A delete runner treats this as success because the requested remote state
    (absence) is already true.
    """
