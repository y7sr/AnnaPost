"""Run queued delete/comment actions."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from time import monotonic

from sqlalchemy import or_, select

from app.core.config import settings
from app.core.locking import generate_worker_id
from app.core.logging import log_runner_execution
from app.db.models.job import InstagramJob, JobStatus, JobType
from app.db.session import async_session_maker
from app.repositories.jobs import claim_job_for_execution
from app.services.actions import execute_action

logger = logging.getLogger(__name__)


async def run() -> int:
    worker, count = generate_worker_id(), 0
    async with async_session_maker() as session:
        jobs = (
            (
                await session.execute(
                    select(InstagramJob).where(
                        or_(
                            InstagramJob.status == JobStatus.PENDING,
                            (InstagramJob.status == JobStatus.RUNNING)
                            & (
                                InstagramJob.locked_at
                                < datetime.now(UTC)
                                - timedelta(seconds=settings.lock_stale_after_seconds)
                            ),
                        ),
                        InstagramJob.job_type.in_(
                            [JobType.DELETE_POST, JobType.CREATE_COMMENT, JobType.REPLY_COMMENT]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        for job in jobs:
            started = monotonic()
            if await claim_job_for_execution(
                session,
                job_id=job.id,
                worker_id=worker,
                now=datetime.now(UTC),
                stale_after_seconds=settings.lock_stale_after_seconds,
            ):
                success = await execute_action(session, job.id)
                count += success
                job = await session.get(InstagramJob, job.id)
                log_runner_execution(
                    logger,
                    runner="actions",
                    operation=job.job_type.value,
                    result="success" if success else "failed",
                    duration=monotonic() - started,
                    job_id=job.id,
                    post_id=job.post_id,
                    account_id=job.account_id,
                    attempt=job.attempts,
                    error_type=None if success else "ActionFailed",
                )
    return count


if __name__ == "__main__":
    print(asyncio.run(run()))
