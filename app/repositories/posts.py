"""Posts repository.

Idempotency & locking (plan.annapost.md §7, §27; phases/02-architecture.md
task 3): claiming a post is a conditional UPDATE + rowcount check, never
read-then-write, so two runner processes can't both "see" the same
ready/scheduled post as available and publish it twice. Zero rows affected
means someone else claimed it first (or it's no longer eligible) — callers
must treat that as "skip", not an error.

`claim_post_for_publishing` commits internally so the claim is its own short
transaction. Callers must not hold this session open across the follow-up
Instagram HTTP call: claim (commits here) -> call Instagram -> write the
result back in a separate transaction/commit. See ARCHITECTURE.md §5/§10.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.post import InstagramPost, PostStatus


async def get_post_by_id(session: AsyncSession, post_id: int) -> InstagramPost | None:
    """Get a post by ID."""
    result = await session.execute(select(InstagramPost).where(InstagramPost.id == post_id))
    return result.scalar_one_or_none()


async def get_post_by_idempotency_key(
    session: AsyncSession, idempotency_key: str
) -> InstagramPost | None:
    """Get a post by its idempotency key."""
    result = await session.execute(
        select(InstagramPost).where(InstagramPost.idempotency_key == idempotency_key)
    )
    return result.scalar_one_or_none()


async def list_posts(
    session: AsyncSession,
    *,
    account_id: int | None = None,
    status: PostStatus | None = None,
    limit: int | None = None,
) -> list[InstagramPost]:
    """List posts with optional filters."""
    query = select(InstagramPost)

    if account_id is not None:
        query = query.where(InstagramPost.account_id == account_id)
    if status is not None:
        query = query.where(InstagramPost.status == status)

    query = query.order_by(InstagramPost.created_at.desc())

    if limit is not None:
        query = query.limit(limit)

    result = await session.execute(query)
    return result.scalars().all()


async def create_post(session: AsyncSession, **kwargs) -> InstagramPost:
    """Create a new post."""
    post = InstagramPost(**kwargs)
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post


async def update_post(session: AsyncSession, post_id: int, **kwargs) -> InstagramPost | None:
    """Update a post by ID."""
    post = await get_post_by_id(session, post_id)
    if post is None:
        return None

    for key, value in kwargs.items():
        if hasattr(post, key):
            setattr(post, key, value)

    await session.commit()
    await session.refresh(post)
    return post


async def delete_post(session: AsyncSession, post_id: int) -> bool:
    """Soft delete a post by setting soft_deleted=True and delete_requested_at.

    Does NOT delete the row - per ARCHITECTURE.md, posts are soft-deleted
    and later reconciled remotely.
    """
    post = await get_post_by_id(session, post_id)
    if post is None:
        return False

    post.soft_deleted = True
    post.delete_requested_at = datetime.utcnow()
    await session.commit()
    await session.refresh(post)
    return True


async def claim_post_for_publishing(
    session: AsyncSession,
    *,
    post_id: int,
    worker_id: str,
    now: datetime,
    stale_after_seconds: int,
) -> bool:
    """Atomically claim a ready/scheduled/failed post for publishing.

    FAILED posts can be claimed for retry (per state machine: failed -> publishing).

    Equivalent to:
        UPDATE instagram_posts
        SET status = 'publishing', locked_at = :now, locked_by = :worker_id
        WHERE id = :id
          AND (status IN ('ready', 'scheduled', 'failed') OR (status = 'publishing' AND locked_at < :stale_cutoff))
          AND (locked_at IS NULL OR locked_at < :stale_cutoff)

    Returns True if this call claimed the row (rowcount == 1). Returns False
    if it was already claimed or is no longer eligible (rowcount == 0) —
    the caller must skip the post, not treat this as an error.
    """
    stale_cutoff = now - timedelta(seconds=stale_after_seconds)

    result = await session.execute(
        update(InstagramPost)
        .execution_options(synchronize_session=False)
        .where(
            InstagramPost.id == post_id,
            or_(
                InstagramPost.status.in_(
                    [PostStatus.READY, PostStatus.SCHEDULED, PostStatus.FAILED]
                ),
                (InstagramPost.status == PostStatus.PUBLISHING)
                & (InstagramPost.locked_at < stale_cutoff),
            ),
            or_(
                InstagramPost.locked_at.is_(None),
                InstagramPost.locked_at < stale_cutoff,
            ),
        )
        .values(
            status=PostStatus.PUBLISHING,
            locked_at=now,
            locked_by=worker_id,
        )
    )
    await session.commit()
    return result.rowcount == 1
