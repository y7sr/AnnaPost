"""Job endpoint contracts."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.job import InstagramJob
from app.db.session import get_db
from app.schemas.job import InstagramJobListResponse, InstagramJobResponse

router = APIRouter(prefix="/jobs")


@router.get("", response_model=InstagramJobListResponse)
async def list_jobs(session: AsyncSession = Depends(get_db)) -> InstagramJobListResponse:
    """List asynchronous jobs and their retry state."""
    rows = (
        (await session.execute(select(InstagramJob).order_by(InstagramJob.created_at.desc())))
        .scalars()
        .all()
    )
    return InstagramJobListResponse(
        jobs=[InstagramJobResponse.model_validate(row) for row in rows], count=len(rows)
    )
