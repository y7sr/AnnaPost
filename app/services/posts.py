"""Posts service."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.event import EventType
from app.db.models.job import InstagramJob, JobStatus, JobType
from app.db.models.post import PostMediaSourceType, PostStatus
from app.repositories.posts import (
    create_post,
    get_post_by_id,
    get_post_by_idempotency_key,
    list_posts,
    update_post,
)
from app.schemas.post import (
    InstagramPostCreate,
    InstagramPostListResponse,
    InstagramPostResponse,
    InstagramPostUpdate,
)
from app.services.accounts import get_enabled_default_account_id
from app.services.events import write_event
from app.services.media_storage import MediaImportError, import_media
from app.services.post_state_machine import validate_transition


async def get_post(service_session: AsyncSession, post_id: int) -> InstagramPostResponse | None:
    """Get a single post by ID."""
    post = await get_post_by_id(service_session, post_id)
    if post is None:
        return None
    return InstagramPostResponse.model_validate(post)


async def get_post_by_key(
    service_session: AsyncSession, idempotency_key: str
) -> InstagramPostResponse | None:
    """Get a post by its idempotency key."""
    post = await get_post_by_idempotency_key(service_session, idempotency_key)
    if post is None:
        return None
    return InstagramPostResponse.model_validate(post)


async def list_all_posts(
    service_session: AsyncSession,
    *,
    account_id: int | None = None,
    status: PostStatus | None = None,
    limit: int | None = None,
) -> InstagramPostListResponse:
    """List posts with optional filters."""
    posts = await list_posts(
        service_session,
        account_id=account_id,
        status=status,
        limit=limit,
    )
    return InstagramPostListResponse(
        posts=[InstagramPostResponse.model_validate(p) for p in posts],
        count=len(posts),
    )


async def create_new_post(
    service_session: AsyncSession, payload: InstagramPostCreate
) -> InstagramPostResponse:
    """Create a new post from the external-producer contract.

    If account_id is not provided, falls back to the enabled default account.
    If no enabled default account exists, raises ValueError.

    Generates idempotency_key if not provided.
    Sets initial status to DRAFT.
    """
    # Resolve account_id: use provided or fall back to default
    account_id = payload.account_id
    if account_id is None:
        default_account_id = await get_enabled_default_account_id(service_session)
        if default_account_id is None:
            raise ValueError(
                "No account_id provided and no enabled default account exists. "
                "Please create and enable a default account first."
            )
        account_id = default_account_id

    # Check for existing post with same idempotency_key
    if payload.idempotency_key is not None:
        existing = await get_post_by_idempotency_key(service_session, payload.idempotency_key)
        if existing is not None:
            # Return the existing post
            return InstagramPostResponse.model_validate(existing)

    # Generate idempotency_key if not provided
    idempotency_key = payload.idempotency_key or f"post_{secrets.token_hex(16)}"

    # Take ownership of the media before creating the durable post/job record.
    # A post never enters the queue with a source that may disappear later.
    try:
        stored_source = await import_media(
            source_type=payload.media_source_type,
            source=payload.media_source,
        )
        stored_payload = payload.media_payload_json
        if payload.media_type.value == "carousel" and stored_payload:
            items = []
            for item in stored_payload["items"]:
                items.append(
                    {
                        **item,
                        "media_source_type": "local_file",
                        "media_source": await import_media(
                            source_type=item["media_source_type"],
                            source=item["media_source"],
                        ),
                    }
                )
            stored_payload = {"items": items}
    except MediaImportError:
        raise

    # Build post data. The original source is intentionally replaced by the
    # durable internal key; the publisher later exposes it temporarily.
    post_data = {
        "account_id": account_id,
        "media_type": payload.media_type,
        "media_source_type": PostMediaSourceType.LOCAL_FILE,
        "media_source": stored_source,
        "media_payload_json": stored_payload,
        "caption": payload.caption,
        "status": PostStatus.SCHEDULED
        if payload.scheduled_at and payload.scheduled_at > datetime.now(UTC)
        else PostStatus.DRAFT,
        "scheduled_at": payload.scheduled_at,
        "idempotency_key": idempotency_key,
        # Lifecycle fields initialized by DB defaults
    }

    post = await create_post(service_session, **post_data)
    await write_event(
        service_session, event_type=EventType.POST_CREATED, account_id=account_id, post_id=post.id
    )
    return InstagramPostResponse.model_validate(post)


async def update_existing_post(
    service_session: AsyncSession,
    post_id: int,
    payload: InstagramPostUpdate,
) -> InstagramPostResponse | None:
    """Update editable post metadata.

    Only allows updates to editable desired-state fields.
    Lifecycle status changes must go through dedicated services that
    use the state machine.
    """
    existing = await get_post_by_id(service_session, post_id)
    if existing is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)

    if "caption" in update_data and existing.status is PostStatus.PUBLISHED:
        # The current Graph client deliberately has no caption-edit operation:
        # retain the local desired value and make that unsupported state explicit.
        update_data["caption_sync_status"] = "unsupported"

    # Update the post
    post = await update_post(service_session, post_id, **update_data)
    if post is None:
        return None
    await write_event(
        service_session,
        event_type=EventType.POST_UPDATED,
        account_id=post.account_id,
        post_id=post.id,
        payload_json={"caption_sync_status": post.caption_sync_status},
    )
    return InstagramPostResponse.model_validate(post)


async def schedule_existing_post(
    service_session: AsyncSession, post_id: int, scheduled_at: datetime
) -> InstagramPostResponse | None:
    post = await get_post_by_id(service_session, post_id)
    if post is None:
        return None
    if scheduled_at.tzinfo is None or scheduled_at <= datetime.now(UTC):
        raise ValueError("scheduled_at must be in the future and timezone-aware")
    validate_transition(post.status, PostStatus.SCHEDULED, raise_on_invalid=True)
    post = await update_post(
        service_session, post_id, scheduled_at=scheduled_at, status=PostStatus.SCHEDULED
    )
    await write_event(
        service_session,
        event_type=EventType.POST_SCHEDULED,
        account_id=post.account_id,
        post_id=post.id,
    )
    return InstagramPostResponse.model_validate(post)


async def queue_publish(service_session: AsyncSession, post_id: int) -> InstagramJob | None:
    post = await get_post_by_id(service_session, post_id)
    if post is None:
        return None

    active_job = (
        await service_session.execute(
            select(InstagramJob)
            .where(
                InstagramJob.post_id == post.id,
                InstagramJob.job_type == JobType.PUBLISH,
                InstagramJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
            )
            .order_by(InstagramJob.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if active_job is not None:
        if post.status is PostStatus.FAILED:
            validate_transition(post.status, PostStatus.READY, raise_on_invalid=True)
            post.status = PostStatus.READY
            post.last_error = None
            if active_job.status is JobStatus.PENDING:
                active_job.run_after = datetime.now(UTC)
            await service_session.commit()
            await service_session.refresh(active_job)
        return active_job

    if post.status in (PostStatus.DRAFT, PostStatus.FAILED):
        validate_transition(post.status, PostStatus.READY, raise_on_invalid=True)
        post.status = PostStatus.READY
        post.last_error = None
    if post.status not in (PostStatus.READY, PostStatus.SCHEDULED):
        raise ValueError(f"Post {post_id} cannot be queued from {post.status.value}")

    # Reuse the failed publication job for an explicit manual retry. This
    # keeps one publication intent per post and resets the retry budget for a
    # new operator-requested attempt cycle.
    failed_job = (
        await service_session.execute(
            select(InstagramJob)
            .where(
                InstagramJob.post_id == post.id,
                InstagramJob.job_type == JobType.PUBLISH,
                InstagramJob.status == JobStatus.FAILED,
            )
            .order_by(InstagramJob.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if failed_job is not None:
        failed_job.status = JobStatus.PENDING
        failed_job.attempts = 0
        failed_job.run_after = datetime.now(UTC)
        failed_job.locked_at = failed_job.locked_by = None
        failed_job.last_error = None
        failed_job.started_at = failed_job.completed_at = None
        await service_session.commit()
        await service_session.refresh(failed_job)
        return failed_job

    job = InstagramJob(
        job_type=JobType.PUBLISH,
        account_id=post.account_id,
        post_id=post.id,
        payload_json={},
        status=JobStatus.PENDING,
    )
    service_session.add(job)
    await service_session.commit()
    await service_session.refresh(job)
    return job


async def request_post_deletion(
    service_session: AsyncSession, post_id: int
) -> InstagramPostResponse | None:
    """Request soft deletion of a post.

    Sets soft_deleted=True and delete_requested_at.
    Does NOT delete the row - per ARCHITECTURE.md, posts are soft-deleted
    and later reconciled remotely.

    The post must be in a state that allows transition to DELETE_REQUESTED
    (currently only PUBLISHED can transition to DELETE_REQUESTED).
    """
    existing = await get_post_by_id(service_session, post_id)
    if existing is None:
        return None

    if existing.status is PostStatus.PUBLISHED:
        validate_transition(existing.status, PostStatus.DELETE_REQUESTED, raise_on_invalid=True)
        existing.status = PostStatus.DELETE_REQUESTED
    elif existing.status in (
        PostStatus.DRAFT,
        PostStatus.READY,
        PostStatus.SCHEDULED,
        PostStatus.FAILED,
    ):
        # There is nothing remote to reconcile. Preserve the record as a
        # soft-deleted local history item and cancel outstanding publication.
        validate_transition(existing.status, PostStatus.CANCELED, raise_on_invalid=True)
        existing.status = PostStatus.CANCELED
        # A failed publication may still have a failed/pending job. Once the
        # post is canceled, those jobs must not be manually or automatically
        # resurrected.
        await service_session.execute(
            update(InstagramJob)
            .where(
                InstagramJob.post_id == existing.id,
                InstagramJob.job_type == JobType.PUBLISH,
                InstagramJob.status.in_([JobStatus.PENDING, JobStatus.FAILED]),
            )
            .values(
                status=JobStatus.CANCELED,
                run_after=None,
                locked_at=None,
                locked_by=None,
            )
        )
    else:
        raise ValueError(f"Post {post_id} cannot be deleted from {existing.status.value}")
    existing.soft_deleted = True
    existing.delete_requested_at = datetime.now(UTC)
    job = None
    if existing.status is PostStatus.DELETE_REQUESTED:
        job = InstagramJob(
            job_type=JobType.DELETE_POST,
            account_id=existing.account_id,
            post_id=existing.id,
            payload_json={},
            status=JobStatus.PENDING,
        )
        service_session.add(job)
    await service_session.commit()
    await service_session.refresh(existing)
    await write_event(
        service_session,
        event_type=EventType.DELETE_REQUESTED,
        account_id=existing.account_id,
        post_id=existing.id,
        job_id=job.id if job else None,
    )
    post = existing
    if post is None:
        return None
    return InstagramPostResponse.model_validate(post)


async def cancel_existing_post(
    service_session: AsyncSession, post_id: int
) -> InstagramPostResponse | None:
    """Cancel an unpublished post and its still-pending publish jobs."""
    post = await get_post_by_id(service_session, post_id)
    if post is None:
        return None
    validate_transition(post.status, PostStatus.CANCELED, raise_on_invalid=True)
    post.status = PostStatus.CANCELED
    await service_session.execute(
        update(InstagramJob)
        .where(
            InstagramJob.post_id == post.id,
            InstagramJob.job_type == JobType.PUBLISH,
            InstagramJob.status.in_([JobStatus.PENDING, JobStatus.FAILED]),
        )
        .values(status=JobStatus.CANCELED, locked_at=None, locked_by=None, run_after=None)
    )
    await service_session.commit()
    await service_session.refresh(post)
    await write_event(
        service_session,
        event_type=EventType.POST_UPDATED,
        account_id=post.account_id,
        post_id=post.id,
        payload_json={"status": PostStatus.CANCELED.value},
    )
    return InstagramPostResponse.model_validate(post)
