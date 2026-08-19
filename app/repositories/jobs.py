"""Repository primitives for the SQLite-backed job queue."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.job import InstagramJob, JobStatus, JobType
from app.db.models.post import InstagramPost, PostStatus


async def list_jobs(
    session: AsyncSession,
    *,
    job_type: object | None = None,
    status: JobStatus | None = None,
    limit: int | None = None,
) -> list[InstagramJob]:
    """List jobs without letting callers construct ORM queries."""
    query = select(InstagramJob).order_by(InstagramJob.created_at.desc())
    if job_type is not None:
        query = query.where(InstagramJob.job_type == job_type)
    if status is not None:
        query = query.where(InstagramJob.status == status)
    if limit is not None:
        query = query.limit(limit)
    return (await session.execute(query)).scalars().all()


async def get_job(session: AsyncSession, job_id: int) -> InstagramJob | None:
    """Get one job by ID."""
    return await session.get(InstagramJob, job_id)


async def retry_failed_job(session: AsyncSession, job_id: int, *, now: datetime) -> bool:
    """Atomically retry a failed job; terminal posts cannot be resurrected."""
    result = await session.execute(
        update(InstagramJob)
        .execution_options(synchronize_session=False)
        .where(
            InstagramJob.id == job_id,
            InstagramJob.status == JobStatus.FAILED,
            # A failed publish job must not be requeued after its post has
            # reached a terminal state. Other job types do not own post
            # lifecycle state and remain retryable independently.
            or_(
                InstagramJob.job_type != JobType.PUBLISH,
                InstagramJob.post_id.is_(None),
                ~select(InstagramPost.id)
                .where(
                    InstagramPost.id == InstagramJob.post_id,
                    InstagramPost.status.in_([PostStatus.CANCELED, PostStatus.DELETED]),
                )
                .exists(),
            ),
        )
        .values(
            status=JobStatus.PENDING,
            attempts=0,
            run_after=now,
            locked_at=None,
            locked_by=None,
            last_error=None,
            started_at=None,
            completed_at=None,
        )
    )
    if result.rowcount == 1:
        # A failed publish can leave a stale post lock after an interrupted
        # worker. Clear it as part of the same retry command so the next
        # claim can perform the valid failed -> publishing transition.
        await session.execute(
            update(InstagramPost)
            .where(
                InstagramPost.id
                == select(InstagramJob.post_id).where(InstagramJob.id == job_id).scalar_subquery()
            )
            .values(locked_at=None, locked_by=None)
        )
    await session.commit()
    return result.rowcount == 1


async def cancel_pending_job(session: AsyncSession, job_id: int) -> bool:
    """Atomically cancel only work that has not been claimed by a runner."""
    result = await session.execute(
        update(InstagramJob)
        .where(InstagramJob.id == job_id, InstagramJob.status == JobStatus.PENDING)
        .values(status=JobStatus.CANCELED, locked_at=None, locked_by=None, run_after=None)
    )
    await session.commit()
    return result.rowcount == 1


async def claim_job_for_execution(
    session: AsyncSession,
    *,
    job_id: int,
    worker_id: str,
    now: datetime,
    stale_after_seconds: int,
) -> bool:
    """Atomically claim one due job for a runner.

    The claim is deliberately its own short transaction.  A caller must
    commit this claim before doing external work, then write the result in a
    separate transaction.  A false return means another worker claimed it,
    it is not due, or it is no longer pending; callers should skip it.

    SQL shape::

        UPDATE instagram_jobs
        SET status = 'running', attempts = attempts + 1,
            started_at = COALESCE(started_at, :now),
            locked_at = :now, locked_by = :worker_id
        WHERE id = :id
          AND (status = 'pending' OR (status = 'running' AND locked_at < :stale_cutoff))
          AND (run_after IS NULL OR run_after <= :now)
    """
    stale_cutoff = now - timedelta(seconds=stale_after_seconds)

    result = await session.execute(
        update(InstagramJob)
        .execution_options(synchronize_session=False)
        .where(
            InstagramJob.id == job_id,
            InstagramJob.attempts < InstagramJob.max_attempts,
            or_(
                # Normal due work.
                InstagramJob.status == JobStatus.PENDING,
                # A process died after claiming work. Its short transaction is
                # stale, so a new runner may safely resume the idempotent job.
                (InstagramJob.status == JobStatus.RUNNING)
                & (InstagramJob.locked_at < stale_cutoff),
            ),
            or_(InstagramJob.run_after.is_(None), InstagramJob.run_after <= now),
        )
        .values(
            status=JobStatus.RUNNING,
            attempts=InstagramJob.attempts + 1,
            started_at=func.coalesce(InstagramJob.started_at, now),
            locked_at=now,
            locked_by=worker_id,
        )
    )
    await session.commit()
    return result.rowcount == 1
