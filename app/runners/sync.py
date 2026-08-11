"""Run due synchronization work."""

import asyncio
import logging
from datetime import UTC, datetime
from time import monotonic

from sqlalchemy import select

from app.core.logging import log_runner_execution
from app.db.models.post import InstagramPost, PostStatus
from app.db.session import async_session_maker
from app.services.options import get_option_value
from app.services.sync import sync_post

logger = logging.getLogger(__name__)


async def run() -> int:
    async with async_session_maker() as session:
        batch = await get_option_value(session, "sync_batch_size", 50)
        limit = batch if isinstance(batch, int) and batch > 0 else 50
        rows = (
            (
                await session.execute(
                    select(InstagramPost)
                    .where(
                        InstagramPost.status == PostStatus.PUBLISHED,
                        InstagramPost.next_sync_at <= datetime.now(UTC),
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        count = 0
        for post in rows:
            started = monotonic()
            success = await sync_post(session, post.id)
            count += success
            log_runner_execution(
                logger,
                runner="sync",
                operation="sync",
                result="success" if success else "failed",
                duration=monotonic() - started,
                post_id=post.id,
                account_id=post.account_id,
                instagram_media_id=post.instagram_media_id,
                error_type=None if success else "SyncFailed",
            )
        return count


if __name__ == "__main__":
    print(asyncio.run(run()))
