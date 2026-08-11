"""Event endpoint contracts."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.event import InstagramEventListResponse
from app.services.events import list_all_events

router = APIRouter(prefix="/events")


@router.get("", response_model=InstagramEventListResponse)
async def list_events(
    account_id: int | None = Query(None),
    post_id: int | None = Query(None),
    job_id: int | None = Query(None),
    limit: int | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> InstagramEventListResponse:
    """List append-only application events."""
    return await list_all_events(
        session,
        account_id=account_id,
        post_id=post_id,
        job_id=job_id,
        limit=limit,
    )
