"""Run due publish jobs safely."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from time import monotonic

from sqlalchemy import or_, select

from app.core.config import settings
from app.core.locking import generate_worker_id
from app.core.logging import log_runner_execution
from app.db.models.job import InstagramJob, JobStatus, JobType
from app.db.models.post import InstagramPost, PostStatus
from app.db.session import async_session_maker
from app.repositories.jobs import claim_job_for_execution
from app.repositories.posts import claim_post_for_publishing
from app.services.options import get_option_value
from app.services.publishing import publish_claimed_post

logger = logging.getLogger(__name__)


async def _run_one_job(session, job: InstagramJob, worker: str) -> bool:
    """Claim and process exactly one job; shared by the batch runner and CLI."""
    started, now = monotonic(), datetime.now(UTC)
    post = await session.get(InstagramPost, job.post_id)
    if post is None or (
        post.status is PostStatus.SCHEDULED
        and post.scheduled_at is not None
        and post.scheduled_at.replace(tzinfo=UTC) > now
    ):
        return False
    if not await claim_job_for_execution(
        session,
        job_id=job.id,
        worker_id=worker,
        now=now,
        stale_after_seconds=settings.lock_stale_after_seconds,
    ):
        return False
    claimed = await claim_post_for_publishing(
        session,
        post_id=job.post_id,
        worker_id=worker,
        now=now,
        stale_after_seconds=settings.lock_stale_after_seconds,
    )
    success = bool(claimed and await publish_claimed_post(session, job.post_id, job_id=job.id))
    job = await session.get(InstagramJob, job.id)
    await session.refresh(job)
    if success and job.status is JobStatus.RUNNING:
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        await session.commit()
    elif not claimed and job.status is JobStatus.RUNNING:
        job.status = JobStatus.PENDING
        job.locked_at = job.locked_by = None
        job.run_after = datetime.now(UTC)
        await session.commit()
    post = await session.get(InstagramPost, job.post_id)
    log_runner_execution(
        logger,
        runner="publish",
        operation="publish",
        result="success" if success else "failed",
        duration=monotonic() - started,
        job_id=job.id,
        post_id=job.post_id,
        account_id=job.account_id,
        instagram_media_id=post.instagram_media_id if post else None,
        attempt=job.attempts,
        error_type=None if success else "PublishFailed",
    )
    return success


async def run_job(job_id: int) -> bool:
    """Run one exact publish job without consuming unrelated queued posts."""
    async with async_session_maker() as session:
        job = await session.get(InstagramJob, job_id)
        if job is None or job.job_type is not JobType.PUBLISH:
            return False
        return await _run_one_job(session, job, generate_worker_id())


async def run() -> int:
    worker, count = generate_worker_id(), 0
    async with async_session_maker() as session:
        batch = await get_option_value(session, "publish_batch_size", 25)
        limit = batch if isinstance(batch, int) and batch > 0 else 25
        jobs = (
            (
                await session.execute(
                    select(InstagramJob)
                    .where(
                        InstagramJob.job_type == JobType.PUBLISH,
                        or_(
                            InstagramJob.status == JobStatus.PENDING,
                            (InstagramJob.status == JobStatus.RUNNING)
                            & (
                                InstagramJob.locked_at
                                < datetime.now(UTC)
                                - timedelta(seconds=settings.lock_stale_after_seconds)
                            ),
                        ),
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        for job in jobs:
            count += int(await _run_one_job(session, job, worker))
    return count


if __name__ == "__main__":
    print(asyncio.run(run()))
