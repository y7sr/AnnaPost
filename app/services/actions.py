"""Execute one claimed action job."""

from contextlib import suppress
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.credentials import resolve_access_token
from app.db.models.account import InstagramAccount
from app.db.models.comment import InstagramComment
from app.db.models.event import EventType
from app.db.models.job import InstagramJob, JobStatus, JobType
from app.db.models.post import InstagramPost, PostStatus
from app.instagram.client import InstagramClient
from app.instagram.errors import InstagramNotFoundError
from app.services.events import write_event
from app.services.retry_policy import configured_retry_delay_seconds


async def execute_action(
    session: AsyncSession, job_id: int, client: InstagramClient | None = None
) -> bool:
    job = await session.get(InstagramJob, job_id)
    # The action runner claims jobs with a bulk UPDATE in this same session.
    # Refresh the identity-mapped row before checking its claimed status.
    if job is not None:
        await session.refresh(job)
    if not job or job.status is not JobStatus.RUNNING:
        return False
    post = await session.get(InstagramPost, job.post_id)
    account = await session.get(InstagramAccount, job.account_id)
    account_id = post.account_id if post else job.account_id
    post_id = post.id if post else job.post_id
    job_type, attempt, max_attempts = job.job_type, job.attempts, job.max_attempts
    try:
        if not post or not account or not account.access_token_ref:
            raise ValueError("Action lacks post or Graph API credentials")
        access_token = resolve_access_token(account.access_token_ref)
        media_id = post.instagram_media_id or ""
        api = client or InstagramClient()
        if job_type is JobType.DELETE_POST:
            await write_event(
                session,
                event_type=EventType.DELETE_STARTED,
                account_id=account_id,
                post_id=post_id,
                job_id=job.id,
            )
        else:
            text = (job.payload_json or {}).get("text")
            if not isinstance(text, str):
                raise ValueError("Action payload lacks text")
        if job_type is JobType.REPLY_COMMENT:
            comment = await session.get(InstagramComment, job.comment_id)
            if not comment:
                raise ValueError("Reply target missing")
            comment_id = comment.instagram_comment_id

        # Fetch everything needed for the remote call, then explicitly end
        # SQLAlchemy's implicit read transaction. A slow Graph request must
        # never retain a SQLite transaction or snapshot.
        await session.rollback()

        if job_type is JobType.DELETE_POST:
            with suppress(InstagramNotFoundError):
                await api.delete_media(access_token=access_token, media_id=media_id)
            post.status, post.deleted_at, post.locked_at, post.locked_by = (
                PostStatus.DELETED,
                datetime.now(UTC),
                None,
                None,
            )
            event = EventType.DELETE_SUCCEEDED
        elif job_type is JobType.CREATE_COMMENT:
            result = await api.create_comment(
                access_token=access_token,
                media_id=media_id,
                text=text,
            )
            await upsert_outgoing(
                session,
                account_id=account_id,
                post_id=post_id,
                instagram_comment_id=result.id,
                text=text,
            )
            event = EventType.COMMENT_SENT
        else:
            result = await api.reply_to_comment(
                access_token=access_token,
                comment_id=comment_id,
                text=text,
            )
            await upsert_outgoing(
                session,
                account_id=account_id,
                post_id=post_id,
                instagram_comment_id=result.id,
                text=text,
                parent=comment_id,
            )
            event = EventType.COMMENT_SENT
        job.status, job.completed_at, job.locked_at, job.locked_by, job.last_error = (
            JobStatus.COMPLETED,
            datetime.now(UTC),
            None,
            None,
            None,
        )
        await session.commit()
        await write_event(
            session, event_type=event, account_id=account_id, post_id=post_id, job_id=job.id
        )
        return True
    except Exception as exc:
        delay = await configured_retry_delay_seconds(session, exc, attempt=attempt)
        job.status = (
            JobStatus.PENDING
            if delay is not None and attempt < max_attempts
            else JobStatus.FAILED
        )
        job.run_after = datetime.now(UTC) + timedelta(seconds=delay) if delay else None
        job.locked_at = job.locked_by = None
        job.last_error = str(exc)
        await session.commit()
        await write_event(
            session,
            event_type=EventType.DELETE_FAILED
            if job_type is JobType.DELETE_POST
            else EventType.COMMENT_FAILED,
            account_id=account_id,
            post_id=post_id,
            job_id=job.id,
            payload_json={"error": str(exc)},
        )
        return False


async def upsert_outgoing(
    session: AsyncSession,
    *,
    account_id: int,
    post_id: int,
    instagram_comment_id: str,
    text: str,
    parent: str | None = None,
) -> None:
    from app.repositories.comments import upsert_comment

    await upsert_comment(
        session,
        account_id=account_id,
        post_id=post_id,
        instagram_comment_id=instagram_comment_id,
        text=text,
        parent_instagram_comment_id=parent,
        is_reply=bool(parent),
        raw_json={},
    )
