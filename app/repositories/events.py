"""Events repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.event import EventType, InstagramEvent


async def create_event(
    session: AsyncSession,
    *,
    event_type: EventType,
    account_id: int | None = None,
    post_id: int | None = None,
    job_id: int | None = None,
    payload_json: dict | None = None,
) -> InstagramEvent:
    """Create a new event.

    Events are append-only - once created, they are never modified.
    """
    event = InstagramEvent(
        event_type=event_type,
        account_id=account_id,
        post_id=post_id,
        job_id=job_id,
        payload_json=payload_json,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def list_events(
    session: AsyncSession,
    *,
    account_id: int | None = None,
    post_id: int | None = None,
    job_id: int | None = None,
    event_type: EventType | None = None,
    limit: int | None = None,
) -> list[InstagramEvent]:
    """List events with optional filters."""
    query = select(InstagramEvent)

    if account_id is not None:
        query = query.where(InstagramEvent.account_id == account_id)
    if post_id is not None:
        query = query.where(InstagramEvent.post_id == post_id)
    if job_id is not None:
        query = query.where(InstagramEvent.job_id == job_id)
    if event_type is not None:
        query = query.where(InstagramEvent.event_type == event_type)

    query = query.order_by(InstagramEvent.created_at.desc())

    if limit is not None:
        query = query.limit(limit)

    result = await session.execute(query)
    return result.scalars().all()
