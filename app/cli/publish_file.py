"""One-shot local-image publishing through ngrok."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.cli.media_staging import (
    MediaStagingError,
    require_image_file,
)
from app.core.credentials import resolve_access_token
from app.db.models.account import InstagramAccount
from app.db.models.post import PostMediaSourceType, PostMediaType
from app.db.session import async_session_maker
from app.repositories.accounts import get_account_by_id, get_enabled_default_account
from app.runners.publish import run_job
from app.schemas.post import InstagramPostCreate
from app.services.jobs import cancel_job
from app.services.posts import create_new_post, get_post, queue_publish


async def _get_publish_account(session: AsyncSession, account_id: int | None) -> InstagramAccount:
    account = (
        await get_account_by_id(session, account_id)
        if account_id is not None
        else await get_enabled_default_account(session)
    )
    if (
        not account
        or not account.enabled
        or not account.instagram_user_id
        or not account.access_token_ref
    ):
        raise MediaStagingError(
            "No enabled publishable account. Configure instagram_user_id, an env: token reference, "
            "and a default account (or pass --account-id)."
        )
    resolve_access_token(account.access_token_ref)
    return account


async def publish_file(
    *,
    image_path: str,
    caption: str | None,
    account_id: int | None,
    idempotency_key: str | None,
) -> dict[str, Any]:
    """Import and publish one local image through the normal durable path."""
    path, content_type = require_image_file(image_path)
    del content_type
    async with async_session_maker() as session:
        account = await _get_publish_account(session, account_id)

    async with async_session_maker() as session:
        post = await create_new_post(
            session,
            InstagramPostCreate(
                account_id=account.id,
                media_type=PostMediaType.IMAGE,
                media_source_type=PostMediaSourceType.LOCAL_FILE,
                media_source=str(path),
                caption=caption,
                idempotency_key=idempotency_key,
            ),
        )
        job = await queue_publish(session, post.id)
        if job is None:
            raise MediaStagingError(f"Could not queue publication for post {post.id}")

    published = await run_job(job.id)
    async with async_session_maker() as session:
        final_post = await get_post(session, post.id)
        if final_post is None:
            raise MediaStagingError(f"Post {post.id} disappeared after publication")
        if not published:
            await cancel_job(session, job.id)
        return {
            "ok": published,
            "post_id": final_post.id,
            "job_id": job.id,
            "status": final_post.status.value,
            "instagram_media_id": final_post.instagram_media_id,
            "permalink": final_post.instagram_permalink,
            "error": final_post.last_error,
        }
