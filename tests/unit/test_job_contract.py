"""Phase 2 task 4 contracts for job payloads and claiming."""

from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models.account import InstagramAccount
from app.db.models.job import InstagramJob, JobStatus, JobType
from app.db.models.post import InstagramPost, PostMediaSourceType, PostMediaType
from app.repositories.jobs import claim_job_for_execution
from app.schemas.job import (
    CreateCommentJobPayload,
    InstagramJobCreate,
    validate_job_payload,
)


async def _make_job(
    session: AsyncSession,
    *,
    run_after=None,
    locked_at=None,
    locked_by=None,
) -> InstagramJob:
    account = InstagramAccount(name="job-test", is_default=True, enabled=True)
    session.add(account)
    await session.flush()
    post = InstagramPost(
        account_id=account.id,
        media_type=PostMediaType.IMAGE,
        media_source_type=PostMediaSourceType.URL,
        media_source="https://example.com/image.jpg",
    )
    session.add(post)
    await session.flush()
    job = InstagramJob(
        job_type=JobType.PUBLISH,
        account_id=account.id,
        post_id=post.id,
        run_after=run_after,
        locked_at=locked_at,
        locked_by=locked_by,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


def test_payload_models_are_selected_by_job_type() -> None:
    payload = validate_job_payload(JobType.CREATE_COMMENT, {"text": "Hello"})
    assert isinstance(payload, CreateCommentJobPayload)
    assert payload.text == "Hello"


def test_payload_bearing_jobs_require_text() -> None:
    with pytest.raises(ValidationError):
        InstagramJobCreate(job_type=JobType.REPLY_COMMENT, payload_json={})


def test_payload_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        validate_job_payload(JobType.PUBLISH, {"unexpected": True})


def test_future_job_types_are_not_accepted() -> None:
    with pytest.raises(ValueError):
        validate_job_payload("refresh_post", {})


async def test_claim_job_marks_running_and_increments_attempts(db_session: AsyncSession) -> None:
    job = await _make_job(db_session)
    now = utcnow()

    claimed = await claim_job_for_execution(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        now=now,
        stale_after_seconds=600,
    )

    assert claimed is True
    await db_session.refresh(job)
    assert job.status == JobStatus.RUNNING
    assert job.attempts == 1
    assert job.started_at == now
    assert job.locked_at == now
    assert job.locked_by == "worker-a"


async def test_second_worker_cannot_claim_running_job(db_session: AsyncSession) -> None:
    job = await _make_job(db_session)
    now = utcnow()
    assert await claim_job_for_execution(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        now=now,
        stale_after_seconds=600,
    )

    assert not await claim_job_for_execution(
        db_session,
        job_id=job.id,
        worker_id="worker-b",
        now=now,
        stale_after_seconds=600,
    )


async def test_stale_pending_lock_can_be_reclaimed(db_session: AsyncSession) -> None:
    now = utcnow()
    job = await _make_job(
        db_session,
        locked_at=now - timedelta(seconds=601),
        locked_by="crashed-worker",
    )

    assert await claim_job_for_execution(
        db_session,
        job_id=job.id,
        worker_id="worker-b",
        now=now,
        stale_after_seconds=600,
    )
    await db_session.refresh(job)
    assert job.locked_by == "worker-b"


async def test_stale_running_job_is_reclaimed_after_a_runner_crash(
    db_session: AsyncSession,
) -> None:
    now = utcnow()
    job = await _make_job(
        db_session,
        locked_at=now - timedelta(seconds=601),
        locked_by="crashed-worker",
    )
    job.status = JobStatus.RUNNING
    await db_session.commit()

    assert await claim_job_for_execution(
        db_session,
        job_id=job.id,
        worker_id="restarted-worker",
        now=now,
        stale_after_seconds=600,
    )
    await db_session.refresh(job)
    assert job.status is JobStatus.RUNNING
    assert job.locked_by == "restarted-worker"
    assert job.attempts == 1


async def test_future_job_is_not_claimed(db_session: AsyncSession) -> None:
    job = await _make_job(db_session, run_after=utcnow() + timedelta(minutes=1))
    assert not await claim_job_for_execution(
        db_session,
        job_id=job.id,
        worker_id="worker-a",
        now=utcnow(),
        stale_after_seconds=600,
    )
