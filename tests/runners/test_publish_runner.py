"""Runner execution tests against one SQLite file; no Graph HTTP is allowed."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.locking import generate_worker_id
from app.db.models.account import InstagramAccount
from app.db.models.job import InstagramJob, JobStatus, JobType
from app.db.models.post import InstagramPost, PostMediaSourceType, PostMediaType, PostStatus
from app.db.session import apply_sqlite_pragmas
from app.repositories.jobs import claim_job_for_execution
from app.repositories.posts import claim_post_for_publishing


async def _runner_sessionmaker(temp_db_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{temp_db_path}", connect_args={"timeout": 5})
    from sqlalchemy import event

    event.listen(
        engine.sync_engine, "connect", lambda connection, _: apply_sqlite_pragmas(connection)
    )
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_publish_job(session: AsyncSession, *, is_default: bool = True) -> tuple[int, int]:
    account = InstagramAccount(
        name="runner", is_default=is_default, instagram_user_id="user", access_token_ref="env:TOKEN"
    )
    post = InstagramPost(
        account=account,
        media_type=PostMediaType.IMAGE,
        media_source_type=PostMediaSourceType.URL,
        media_source="https://example.test/image.jpg",
        status=PostStatus.READY,
    )
    job = InstagramJob(
        job_type=JobType.PUBLISH, account=account, post=post, status=JobStatus.PENDING
    )
    session.add_all([account, post, job])
    await session.commit()
    return post.id, job.id


async def test_two_publish_runners_contend_without_duplicates(temp_db_path, monkeypatch) -> None:
    """Two independently-created runner sessions race; exactly one performs work."""
    import app.runners.publish as publish_runner

    engine, sessions = await _runner_sessionmaker(temp_db_path)
    async with sessions() as seed_session:
        post_id, job_id = await _seed_publish_job(seed_session)

    calls = 0

    async def fake_publish(session: AsyncSession, post_id: int, *, job_id: int) -> bool:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        post = await session.get(InstagramPost, post_id)
        assert post is not None
        post.status = PostStatus.PUBLISHED
        post.instagram_media_id = "mock-media"
        post.locked_at = post.locked_by = None
        await session.commit()
        return True

    try:
        monkeypatch.setattr(publish_runner, "async_session_maker", sessions)
        monkeypatch.setattr(publish_runner, "publish_claimed_post", fake_publish)
        results = await asyncio.gather(publish_runner.run(), publish_runner.run())
        assert sorted(results) == [0, 1]
        assert calls == 1

        async with sessions() as check_session:
            job = await check_session.get(InstagramJob, job_id)
            post = await check_session.get(InstagramPost, post_id)
            assert job is not None and job.status is JobStatus.COMPLETED
            assert post is not None and post.status is PostStatus.PUBLISHED
    finally:
        await engine.dispose()


async def test_crashed_claim_is_recovered_by_the_publish_runner(temp_db_path, monkeypatch) -> None:
    """A stale running job/post is resumed by a later runner invocation."""
    import app.runners.publish as publish_runner
    from app.db.base import utcnow

    engine, sessions = await _runner_sessionmaker(temp_db_path)
    async with sessions() as session:
        post_id, job_id = await _seed_publish_job(session)
        now = utcnow()
        assert await claim_job_for_execution(
            session, job_id=job_id, worker_id=generate_worker_id(), now=now, stale_after_seconds=600
        )
        assert await claim_post_for_publishing(
            session,
            post_id=post_id,
            worker_id=generate_worker_id(),
            now=now,
            stale_after_seconds=600,
        )
        job = await session.get(InstagramJob, job_id)
        post = await session.get(InstagramPost, post_id)
        assert job is not None and post is not None
        job.locked_at = post.locked_at = now - timedelta(
            seconds=settings.lock_stale_after_seconds + 1
        )
        await session.commit()

    async def fake_publish(session: AsyncSession, post_id: int, *, job_id: int) -> bool:
        post = await session.get(InstagramPost, post_id)
        assert post is not None
        post.status = PostStatus.PUBLISHED
        post.locked_at = post.locked_by = None
        await session.commit()
        return True

    try:
        monkeypatch.setattr(publish_runner, "async_session_maker", sessions)
        monkeypatch.setattr(publish_runner, "publish_claimed_post", fake_publish)
        assert await publish_runner.run() == 1
    finally:
        await engine.dispose()


async def test_run_job_only_processes_the_requested_job(temp_db_path, monkeypatch) -> None:
    """The one-shot CLI path must never consume another pending post."""
    import app.runners.publish as publish_runner

    engine, sessions = await _runner_sessionmaker(temp_db_path)
    async with sessions() as session:
        first_post_id, first_job_id = await _seed_publish_job(session)
        _, second_job_id = await _seed_publish_job(session, is_default=False)

    received_post_ids: list[int] = []

    async def fake_publish(session: AsyncSession, post_id: int, *, job_id: int) -> bool:
        received_post_ids.append(post_id)
        post = await session.get(InstagramPost, post_id)
        assert post is not None
        post.status = PostStatus.PUBLISHED
        post.locked_at = post.locked_by = None
        await session.commit()
        return True

    try:
        monkeypatch.setattr(publish_runner, "async_session_maker", sessions)
        monkeypatch.setattr(publish_runner, "publish_claimed_post", fake_publish)
        assert await publish_runner.run_job(first_job_id)
        assert received_post_ids == [first_post_id]
        async with sessions() as session:
            second_job = await session.get(InstagramJob, second_job_id)
            assert second_job is not None and second_job.status is JobStatus.PENDING
    finally:
        await engine.dispose()


async def test_action_runner_executes_a_claimed_action_once(temp_db_path, monkeypatch) -> None:
    import app.runners.actions as actions_runner

    engine, sessions = await _runner_sessionmaker(temp_db_path)
    async with sessions() as session:
        post_id, _ = await _seed_publish_job(session)
        post = await session.get(InstagramPost, post_id)
        assert post is not None
        job = InstagramJob(
            job_type=JobType.DELETE_POST,
            account_id=post.account_id,
            post_id=post.id,
            status=JobStatus.PENDING,
        )
        session.add(job)
        await session.commit()

    async def fake_execute(session: AsyncSession, job_id: int) -> bool:
        job = await session.get(InstagramJob, job_id)
        assert job is not None
        job.status = JobStatus.COMPLETED
        await session.commit()
        return True

    try:
        monkeypatch.setattr(actions_runner, "async_session_maker", sessions)
        monkeypatch.setattr(actions_runner, "execute_action", fake_execute)
        assert await actions_runner.run() == 1
    finally:
        await engine.dispose()


async def test_sync_runner_executes_due_post_once(temp_db_path, monkeypatch) -> None:
    import app.runners.sync as sync_runner

    engine, sessions = await _runner_sessionmaker(temp_db_path)
    async with sessions() as session:
        post_id, _ = await _seed_publish_job(session)
        post = await session.get(InstagramPost, post_id)
        assert post is not None
        post.status = PostStatus.PUBLISHED
        post.instagram_media_id = "mock-media"
        post.next_sync_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    calls = 0

    async def fake_sync(_: AsyncSession, received_post_id: int) -> bool:
        nonlocal calls
        assert received_post_id == post_id
        calls += 1
        return True

    try:
        monkeypatch.setattr(sync_runner, "async_session_maker", sessions)
        monkeypatch.setattr(sync_runner, "sync_post", fake_sync)
        assert await sync_runner.run() == 1
        assert calls == 1
    finally:
        await engine.dispose()
