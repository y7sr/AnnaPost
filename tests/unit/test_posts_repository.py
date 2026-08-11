"""Tests for the post claiming primitive (phases/02-architecture.md task 3)."""

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models.account import InstagramAccount
from app.db.models.post import InstagramPost, PostMediaSourceType, PostMediaType, PostStatus
from app.repositories.posts import claim_post_for_publishing

STALE_AFTER_SECONDS = 600


async def _make_post(session: AsyncSession, status: PostStatus, **overrides) -> InstagramPost:
    account = InstagramAccount(name="test", is_default=True, enabled=True)
    session.add(account)
    await session.flush()

    post = InstagramPost(
        account_id=account.id,
        media_type=PostMediaType.IMAGE,
        media_source_type=PostMediaSourceType.URL,
        media_source="https://example.com/x.jpg",
        status=status,
        **overrides,
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post


@pytest.mark.parametrize("status", [PostStatus.READY, PostStatus.SCHEDULED, PostStatus.FAILED])
async def test_claim_succeeds_for_eligible_status(db_session: AsyncSession, status) -> None:
    post = await _make_post(db_session, status)
    now = utcnow()

    claimed = await claim_post_for_publishing(
        db_session,
        post_id=post.id,
        worker_id="host:1:abcd1234",
        now=now,
        stale_after_seconds=STALE_AFTER_SECONDS,
    )

    assert claimed is True
    await db_session.refresh(post)
    assert post.status == PostStatus.PUBLISHING
    assert post.locked_at == now
    assert post.locked_by == "host:1:abcd1234"


@pytest.mark.parametrize(
    "status",
    [
        PostStatus.DRAFT,
        PostStatus.PUBLISHING,
        PostStatus.PUBLISHED,
        PostStatus.DELETE_REQUESTED,
        PostStatus.DELETED,
        PostStatus.CANCELED,
    ],
)
async def test_claim_fails_for_ineligible_status(db_session: AsyncSession, status) -> None:
    post = await _make_post(db_session, status)

    claimed = await claim_post_for_publishing(
        db_session,
        post_id=post.id,
        worker_id="host:1:abcd1234",
        now=utcnow(),
        stale_after_seconds=STALE_AFTER_SECONDS,
    )

    assert claimed is False
    await db_session.refresh(post)
    assert post.status == status
    assert post.locked_by is None


async def test_claim_fails_when_freshly_locked_by_another_worker(db_session: AsyncSession) -> None:
    now = utcnow()
    post = await _make_post(
        db_session,
        PostStatus.READY,
        locked_at=now,
        locked_by="other-worker",
    )

    claimed = await claim_post_for_publishing(
        db_session,
        post_id=post.id,
        worker_id="me",
        now=now + timedelta(seconds=1),
        stale_after_seconds=STALE_AFTER_SECONDS,
    )

    assert claimed is False
    await db_session.refresh(post)
    assert post.status == PostStatus.READY
    assert post.locked_by == "other-worker"


async def test_claim_succeeds_when_lock_is_stale(db_session: AsyncSession) -> None:
    stale_lock_time = utcnow() - timedelta(seconds=STALE_AFTER_SECONDS + 1)
    post = await _make_post(
        db_session,
        PostStatus.READY,
        locked_at=stale_lock_time,
        locked_by="crashed-worker",
    )
    now = utcnow()

    claimed = await claim_post_for_publishing(
        db_session,
        post_id=post.id,
        worker_id="new-worker",
        now=now,
        stale_after_seconds=STALE_AFTER_SECONDS,
    )

    assert claimed is True
    await db_session.refresh(post)
    assert post.status == PostStatus.PUBLISHING
    assert post.locked_at == now
    assert post.locked_by == "new-worker"


async def test_stale_publishing_post_is_reclaimed_after_a_runner_crash(
    db_session: AsyncSession,
) -> None:
    now = utcnow()
    post = await _make_post(
        db_session,
        PostStatus.PUBLISHING,
        locked_at=now - timedelta(seconds=STALE_AFTER_SECONDS + 1),
        locked_by="crashed-worker",
    )

    assert await claim_post_for_publishing(
        db_session,
        post_id=post.id,
        worker_id="restarted-worker",
        now=now,
        stale_after_seconds=STALE_AFTER_SECONDS,
    )
    await db_session.refresh(post)
    assert post.status is PostStatus.PUBLISHING
    assert post.locked_by == "restarted-worker"


async def test_second_claim_attempt_is_rejected(db_session: AsyncSession) -> None:
    """Simulates two runner processes racing for the same post: only the first wins."""
    post = await _make_post(db_session, PostStatus.READY)
    now = utcnow()

    first = await claim_post_for_publishing(
        db_session,
        post_id=post.id,
        worker_id="worker-a",
        now=now,
        stale_after_seconds=STALE_AFTER_SECONDS,
    )
    second = await claim_post_for_publishing(
        db_session,
        post_id=post.id,
        worker_id="worker-b",
        now=now,
        stale_after_seconds=STALE_AFTER_SECONDS,
    )

    assert first is True
    assert second is False
    await db_session.refresh(post)
    assert post.locked_by == "worker-a"


async def test_claim_of_nonexistent_post_returns_false(db_session: AsyncSession) -> None:
    claimed = await claim_post_for_publishing(
        db_session,
        post_id=999999,
        worker_id="worker-a",
        now=utcnow(),
        stale_after_seconds=STALE_AFTER_SECONDS,
    )

    assert claimed is False
