"""Metric endpoint contracts."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.metrics import list_snapshots
from app.schemas.metrics import InstagramPostMetricListResponse, InstagramPostMetricResponse

router = APIRouter()


@router.get("/posts/{post_id}/metrics", response_model=InstagramPostMetricListResponse)
async def list_post_metrics(
    post_id: int, session: AsyncSession = Depends(get_db)
) -> InstagramPostMetricListResponse:
    """List append-only metric snapshots for one post."""
    rows = await list_snapshots(session, post_id)
    return InstagramPostMetricListResponse(
        metrics=[InstagramPostMetricResponse.model_validate(row) for row in rows], count=len(rows)
    )
