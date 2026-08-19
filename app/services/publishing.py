"""Publish one safely claimed post; HTTP is strictly outside the claim transaction."""

from __future__ import annotations

import logging
import mimetypes
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.cli.media_staging import MediaStagingError, NgrokTunnel, SingleFileServer
from app.core.credentials import resolve_access_token
from app.db.models.account import InstagramAccount
from app.db.models.event import EventType
from app.db.models.job import InstagramJob, JobStatus
from app.db.models.post import PostMediaSourceType, PostMediaType, PostStatus
from app.instagram.client import InstagramClient
from app.instagram.errors import InstagramTransientError
from app.instagram.schemas import InstagramCarouselItem
from app.services.events import write_event
from app.services.media import UrlMediaResolver
from app.services.media_storage import storage_path
from app.services.retry_policy import configured_retry_delay_seconds

if TYPE_CHECKING:
    from app.db.models.post import InstagramPost, PostMediaSourceType


async def _validate_account(account: InstagramAccount | None) -> str:
    """Validate that the account is enabled and has valid credentials.

    Args:
        account: The Instagram account to validate.

    Returns:
        The resolved access token.

    Raises:
        ValueError: If the account is not valid or lacks credentials.
        CredentialResolutionError: If the access token cannot be resolved.
    """
    if (
        not account
        or not account.enabled
        or not account.instagram_user_id
        or not account.access_token_ref
    ):
        raise ValueError("Account lacks enabled Graph API credentials")
    return resolve_access_token(account.access_token_ref)


async def _resolve_media_source(
    resolver: UrlMediaResolver,
    source_type: PostMediaSourceType,
    source: str,
) -> str:
    """Resolve a media source to a fetchable URL.

    Args:
        resolver: The media resolver instance.
        source_type: The type of media source.
        source: The source identifier (e.g., URL).

    Returns:
        The resolved URL.

    Raises:
        MediaResolutionError: If the source cannot be resolved.
    """
    return await resolver.resolve(source_type=source_type, source=source)


async def _create_carousel_items(
    resolver: UrlMediaResolver,
    items: list[dict],
) -> list[InstagramCarouselItem]:
    """Create carousel items by resolving all media sources.

    Args:
        resolver: The media resolver instance.
        items: List of dicts with media_type, media_source_type, and media_source keys.

    Returns:
        List of resolved InstagramCarouselItem objects.
    """
    from app.db.models.post import PostMediaSourceType

    return [
        InstagramCarouselItem(
            media_type=x["media_type"],
            media_url=await resolver.resolve(
                source_type=PostMediaSourceType(x["media_source_type"]),
                source=x["media_source"],
            ),
        )
        for x in items
    ]


async def _create_container(
    session: AsyncSession,
    api: InstagramClient,
    access_token: str,
    instagram_user_id: str,
    post: InstagramPost,
    resolved_source: str,
    resolver: UrlMediaResolver,
) -> str:
    """Create an Instagram media container for the post.

    Handles IMAGE, REEL, and CAROUSEL media types. For CAROUSEL, resolves all
    child media sources. Persists the container_id to the post before returning.

    Args:
        session: The database session.
        api: The Instagram client.
        access_token: The resolved access token.
        instagram_user_id: The Instagram user ID.
        post: The post being published.
        resolved_source: The resolved source URL for the main media.
        resolver: The media resolver instance (for carousel children).

    Returns:
        The container ID.

    Raises:
        Exception: Any error from the Instagram API calls.
    """
    container_id = post.instagram_container_id
    if container_id is not None:
        return container_id

    if post.media_type is PostMediaType.IMAGE:
        container = await api.create_image_container(
            instagram_user_id=instagram_user_id,
            access_token=access_token,
            image_url=resolved_source,
            caption=post.caption,
        )
    elif post.media_type is PostMediaType.REEL:
        container = await api.create_reel_container(
            instagram_user_id=instagram_user_id,
            access_token=access_token,
            video_url=resolved_source,
            caption=post.caption,
        )
    else:
        items = await _create_carousel_items(resolver, post.media_payload_json["items"])
        container = await api.create_carousel_container(
            instagram_user_id=instagram_user_id,
            access_token=access_token,
            items=items,
            caption=post.caption,
        )

    container_id = container.id
    # Persist before the external publish call: a crash/rerun reuses this
    # exact remote container instead of creating another one.
    post.instagram_container_id = container_id
    await session.commit()
    return container_id


async def _handle_publish_success(
    session: AsyncSession,
    api: InstagramClient,
    access_token: str,
    instagram_user_id: str,
    container_id: str,
    post: InstagramPost,
) -> None:
    """Handle a successful publish operation.

    Updates the post with Instagram metadata, writes success event.
    Explicitly handles ambiguous timeouts after media_publish: if the
    publish_container call succeeds but the subsequent get_media call
    fails with a timeout or transient error, we still consider the publish
    successful since we have the media_id from publish_container.

    Args:
        session: The database session.
        api: The Instagram client.
        access_token: The resolved access token.
        instagram_user_id: The Instagram user ID.
        container_id: The container ID that was published.
        post: The post being published.
    """
    published = await api.publish_container(
        instagram_user_id=instagram_user_id,
        access_token=access_token,
        container_id=container_id,
    )

    # Try to fetch media details. If this fails with a transient error
    # (timeout, network failure, or 5xx), we still have the media_id from
    # publish_container, so the publish itself succeeded. We just won't have
    # permalink/caption yet. This explicitly handles the "ambiguous timeout
    # after media_publish" scenario where publish_container returned success
    # but get_media failed due to a transient issue.
    try:
        remote = await api.get_media(access_token=access_token, media_id=published.id)
        permalink = remote.permalink
        caption = remote.caption
        caption_sync_status = "in_sync"
    except InstagramTransientError as exc:
        # Transient failure (timeout, network error, 5xx) getting media details
        # after successful publish_container. Log this but don't fail the publish
        # - we have the media_id from publish_container, so the publish succeeded.
        # The metadata (permalink, caption) can be synced later via a sync runner.
        logger = logging.getLogger(__name__)
        logger.warning(
            "Ambiguous timeout after media_publish for post %s: publish_container "
            "succeeded (media_id=%s) but get_media failed with transient error: %s. "
            "Marking as published with minimal metadata; sync can retry later.",
            post.id,
            published.id,
            exc,
        )
        permalink = None
        caption = None
        caption_sync_status = "sync_pending"

    post.instagram_container_id, post.instagram_media_id, post.instagram_permalink = (
        container_id,
        published.id,
        permalink,
    )
    post.published_at, post.status, post.last_error, post.locked_at, post.locked_by = (
        datetime.now(UTC),
        PostStatus.PUBLISHED,
        None,
        None,
        None,
    )
    post.remote_caption_last_known = caption
    post.caption_sync_status = caption_sync_status
    await session.commit()

    await write_event(
        session,
        event_type=EventType.PUBLISH_SUCCEEDED,
        account_id=post.account_id,
        post_id=post.id,
        payload_json={"instagram_media_id": published.id},
    )


async def _handle_publish_failure(
    session: AsyncSession,
    exc: Exception,
    post: InstagramPost,
    job_id: int | None = None,
) -> None:
    """Handle a failed publish operation.

    Updates the post to FAILED state, updates the job if provided for retry logic,
    and writes failure event.

    Args:
        session: The database session.
        exc: The exception that caused the failure.
        post: The post that failed to publish.
        job_id: Optional job ID for retry handling.
    """
    post.status, post.last_error, post.locked_at, post.locked_by = (
        PostStatus.FAILED,
        str(exc),
        None,
        None,
    )
    await session.commit()

    if job_id is not None:
        job = await session.get(InstagramJob, job_id)
        if job is not None:
            delay = await configured_retry_delay_seconds(session, exc, attempt=job.attempts)
            job.status = (
                JobStatus.PENDING
                if delay is not None and job.attempts < job.max_attempts
                else JobStatus.FAILED
            )
            job.run_after = datetime.now(UTC) + timedelta(seconds=delay) if delay else None
            job.locked_at = job.locked_by = None
            job.last_error = str(exc)
            await session.commit()

    await write_event(
        session,
        event_type=EventType.PUBLISH_FAILED,
        account_id=post.account_id,
        post_id=post.id,
        payload_json={"error": str(exc)},
    )


async def publish_claimed_post(
    session: AsyncSession,
    post_id: int,
    client: InstagramClient | None = None,
    job_id: int | None = None,
) -> bool:
    """Publish a safely claimed post to Instagram.

    The post must already be in PUBLISHING status (claimed via claim_post_for_publishing).
    This function handles the entire publish workflow including:
    - Account and post validation
    - Media source resolution
    - Container creation (if not already created)
    - Container publishing
    - Success/failure handling with proper state updates

    If container creation succeeds but publishing fails, the container_id is
    persisted so a retry will reuse the same container instead of creating a new one.

    Args:
        session: The database session.
        post_id: The ID of the post to publish.
        client: Optional Instagram client (defaults to shared client).
        job_id: Optional job ID for retry tracking.

    Returns:
        True if publishing succeeded, False otherwise.
    """
    from app.repositories.posts import get_post_by_id

    post = await get_post_by_id(session, post_id)
    # ``claim_post_for_publishing`` uses a bulk UPDATE in the same session.
    # SQLAlchemy keeps an already-loaded identity-map instance unchanged after
    # that operation, so refresh before enforcing the claimed-state guard.
    # Without this, a freshly claimed READY post can look stale here and the
    # runner exits without making the provider call.
    if post is not None:
        await session.refresh(post)
    if not post or post.status is not PostStatus.PUBLISHING:
        return False

    account = await session.get(InstagramAccount, post.account_id)

    try:
        access_token = await _validate_account(account)

        await write_event(
            session,
            event_type=EventType.PUBLISH_STARTED,
            account_id=post.account_id,
            post_id=post.id,
        )

        resolver, api = UrlMediaResolver(), client or InstagramClient()

        if post.media_source_type is PostMediaSourceType.LOCAL_FILE:
            # The file is durable, but Instagram still needs a temporary
            # public HTTPS URL. Keep the tunnel alive for the complete remote
            # container + publish sequence so retries remain possible later.
            source_path = storage_path(post.media_source)
            if not source_path.is_file():
                raise MediaStagingError(f"Stored media file is missing: {post.media_source}")
            content_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
            with SingleFileServer(source_path, content_type) as media_server:
                tunnel = NgrokTunnel(media_server.origin_url)
                try:
                    public_origin = await tunnel.start()
                    source = f"{public_origin}{media_server.route}"
                    container_id = await _create_container(
                        session,
                        api,
                        access_token,
                        account.instagram_user_id,
                        post,
                        source,
                        resolver,
                    )
                    await _handle_publish_success(
                        session,
                        api,
                        access_token,
                        account.instagram_user_id,
                        container_id,
                        post,
                    )
                finally:
                    await tunnel.stop()
        else:
            source = await _resolve_media_source(
                resolver, post.media_source_type, post.media_source
            )
            container_id = await _create_container(
                session, api, access_token, account.instagram_user_id, post, source, resolver
            )
            await _handle_publish_success(
                session, api, access_token, account.instagram_user_id, container_id, post
            )

        return True

    except Exception as exc:
        await _handle_publish_failure(session, exc, post, job_id)
        return False
