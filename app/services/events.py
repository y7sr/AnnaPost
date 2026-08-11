"""Events service.

Append-only event writing. Called from services and runners at event points
listed in ARCHITECTURE.md section 15.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.event import EventType, InstagramEvent
from app.repositories.events import create_event, list_events
from app.schemas.event import InstagramEventListResponse, InstagramEventResponse


async def write_event(
    session: AsyncSession,
    *,
    event_type: EventType,
    account_id: int | None = None,
    post_id: int | None = None,
    job_id: int | None = None,
    payload_json: dict | None = None,
) -> InstagramEvent:
    """Write an event to the append-only log.

    This is the primary interface for recording events. Services and runners
    call this at the event points defined in the architecture:
    - post_created, post_updated, post_scheduled
    - publish_started, publish_succeeded, publish_failed
    - sync_started, sync_succeeded, sync_failed
    - metric_snapshot_created
    - delete_requested, delete_started, delete_succeeded, delete_failed
    - comment_received, comment_queued, comment_sent, comment_failed

    Args:
        session: Database session
        event_type: The type of event being recorded
        account_id: Optional associated account ID
        post_id: Optional associated post ID
        job_id: Optional associated job ID
        payload_json: Optional event-specific payload data

    Returns:
        The created InstagramEvent
    """
    return await create_event(
        session,
        event_type=event_type,
        account_id=account_id,
        post_id=post_id,
        job_id=job_id,
        payload_json=payload_json,
    )


async def list_all_events(
    session: AsyncSession,
    *,
    account_id: int | None = None,
    post_id: int | None = None,
    job_id: int | None = None,
    limit: int | None = None,
) -> InstagramEventListResponse:
    """List events with optional filters."""
    events = await list_events(
        session,
        account_id=account_id,
        post_id=post_id,
        job_id=job_id,
        limit=limit,
    )
    return InstagramEventListResponse(
        events=[InstagramEventResponse.model_validate(e) for e in events],
        count=len(events),
    )
