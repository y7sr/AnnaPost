"""Logging configuration."""

import logging
import sys
from json import dumps
from typing import Any

from app.core.config import settings


def setup_logging() -> None:
    """Configure application logging."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Set the root logger level
    root_logger = logging.getLogger()
    root_logger.setLevel(level)


def log_runner_execution(
    logger: logging.Logger,
    *,
    runner: str,
    operation: str,
    result: str,
    duration: float,
    job_id: int | None = None,
    post_id: int | None = None,
    account_id: int | None = None,
    instagram_media_id: str | None = None,
    attempt: int | None = None,
    error_type: str | None = None,
) -> None:
    """Write one safe, structured runner diagnostic.

    Deliberately accept only identifiers and error classes. Request payloads,
    response bodies, captions, and credentials never reach operational logs.
    """
    fields: dict[str, Any] = {
        "runner": runner,
        "job_id": job_id,
        "post_id": post_id,
        "account_id": account_id,
        "instagram_media_id": instagram_media_id,
        "operation": operation,
        "attempt": attempt,
        "duration": round(duration, 3),
        "result": result,
        "error_type": error_type,
    }
    logger.info("runner_execution %s", dumps(fields, sort_keys=True))
