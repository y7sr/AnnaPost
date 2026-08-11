"""Admin routes for Instagram events."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.template_utils import render_template
from app.db.models.event import InstagramEvent
from app.db.session import get_db
from app.schemas.event import InstagramEventResponse

router = APIRouter()


@router.get("/")
async def list_events_page(
    request: Request,
    account_id: int | None = None,
    post_id: int | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_db),
):
    """Render events list page."""
    query = select(InstagramEvent).order_by(InstagramEvent.created_at.desc())

    if account_id:
        query = query.where(InstagramEvent.account_id == account_id)
    if post_id:
        query = query.where(InstagramEvent.post_id == post_id)

    result = await session.execute(query.limit(limit))
    events = result.scalars().all()
    event_responses = [InstagramEventResponse.model_validate(event) for event in events]

    return render_template(
        "events.html",
        request=request,
        events=event_responses,
        count=len(event_responses),
        account_id_filter=account_id,
        post_id_filter=post_id,
    )


@router.get("/{event_id}/")
async def get_event_page(
    request: Request,
    event_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Render event detail page."""
    event = await session.get(InstagramEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    return render_template(
        "event_detail.html",
        request=request,
        event=InstagramEventResponse.model_validate(event),
    )
