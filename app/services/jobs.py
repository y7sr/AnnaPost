"""Service boundary for operator-facing job observation and commands."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.job import JobStatus, JobType
from app.repositories.jobs import cancel_pending_job, get_job, list_jobs, retry_failed_job
from app.schemas.job import InstagramJobListResponse, InstagramJobResponse


async def list_all_jobs(
    session: AsyncSession,
    *,
    job_type: JobType | None = None,
    status: JobStatus | None = None,
    limit: int | None = None,
) -> InstagramJobListResponse:
    rows = await list_jobs(session, job_type=job_type, status=status, limit=limit)
    return InstagramJobListResponse(
        jobs=[InstagramJobResponse.model_validate(row) for row in rows], count=len(rows)
    )


async def get_job_status(session: AsyncSession, job_id: int) -> InstagramJobResponse | None:
    job = await get_job(session, job_id)
    return InstagramJobResponse.model_validate(job) if job else None


async def retry_job(session: AsyncSession, job_id: int) -> bool:
    """Retry only a failed job; callers map False to a conflict/not-found response."""
    return await retry_failed_job(session, job_id, now=datetime.now(UTC))


async def cancel_job(session: AsyncSession, job_id: int) -> bool:
    """Cancel only pending work; claimed work must reach a runner-defined terminal state."""
    return await cancel_pending_job(session, job_id)
