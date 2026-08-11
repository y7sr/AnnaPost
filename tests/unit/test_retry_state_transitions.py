"""Retry state invariants for jobs and their owning posts."""

from datetime import UTC, datetime

from app.db.models.account import InstagramAccount
from app.db.models.job import InstagramJob, JobStatus, JobType
from app.db.models.post import InstagramPost, PostMediaSourceType, PostMediaType, PostStatus
from app.repositories.jobs import claim_job_for_execution, retry_failed_job
from app.services.posts import queue_publish, request_post_deletion


async def _publish_fixture(session, *, post_status=PostStatus.FAILED, job_status=JobStatus.FAILED):
    account = InstagramAccount(name="retry", is_default=True, enabled=True)
    post = InstagramPost(
        account=account,
        media_type=PostMediaType.IMAGE,
        media_source_type=PostMediaSourceType.URL,
        media_source="https://example.test/image.jpg",
        status=post_status,
    )
    job = InstagramJob(
        job_type=JobType.PUBLISH,
        account=account,
        post=post,
        status=job_status,
        attempts=3,
        max_attempts=3,
        locked_at=datetime.now(UTC),
        locked_by="stale-worker",
    )
    session.add_all([account, post, job])
    await session.commit()
    return post, job


async def test_claim_does_not_cross_max_attempts(db_session) -> None:
    _, job = await _publish_fixture(db_session, job_status=JobStatus.PENDING)

    assert not await claim_job_for_execution(
        db_session,
        job_id=job.id,
        worker_id="worker",
        now=datetime.now(UTC),
        stale_after_seconds=600,
    )


async def test_manual_retry_resets_job_and_releases_post_lock(db_session) -> None:
    post, job = await _publish_fixture(db_session)

    assert await retry_failed_job(db_session, job.id, now=datetime.now(UTC))
    await db_session.refresh(post)
    await db_session.refresh(job)
    assert job.status is JobStatus.PENDING
    assert job.attempts == 0
    assert job.locked_at is None
    assert post.locked_at is None
    assert post.status is PostStatus.FAILED


async def test_queue_publish_moves_failed_post_to_ready_and_reuses_job(db_session) -> None:
    post, job = await _publish_fixture(db_session)
    job_id = job.id

    queued = await queue_publish(db_session, post.id)

    await db_session.refresh(post)
    assert queued is not None
    await db_session.refresh(queued)
    assert queued.id == job_id
    assert queued.status is JobStatus.PENDING
    assert queued.attempts == 0
    assert post.status is PostStatus.READY
    assert post.last_error is None


async def test_canceling_failed_post_cancels_publish_retry(db_session) -> None:
    post, job = await _publish_fixture(db_session)

    deleted = await request_post_deletion(db_session, post.id)

    assert deleted is not None
    await db_session.refresh(job)
    assert deleted.status is PostStatus.CANCELED
    assert job.status is JobStatus.CANCELED
    assert not await retry_failed_job(db_session, job.id, now=datetime.now(UTC))


async def test_retry_does_not_resurrect_terminal_post(db_session) -> None:
    _, job = await _publish_fixture(db_session, post_status=PostStatus.CANCELED)

    assert not await retry_failed_job(db_session, job.id, now=datetime.now(UTC))
