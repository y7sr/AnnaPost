"""Asynchronous outgoing-comment services and read models."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.job import InstagramJob, JobStatus, JobType
from app.repositories.comments import get_comment, list_comments
from app.repositories.posts import get_post_by_id
from app.schemas.comment import InstagramCommentListResponse, InstagramCommentResponse
from app.schemas.job import InstagramJobResponse


async def list_post_comments(session: AsyncSession, post_id: int) -> InstagramCommentListResponse:
    rows = await list_comments(session, post_id)
    return InstagramCommentListResponse(
        comments=[InstagramCommentResponse.model_validate(row) for row in rows], count=len(rows)
    )


async def queue_comment(session: AsyncSession, post_id: int, text: str) -> InstagramJob | None:
    post = await get_post_by_id(session, post_id)
    if not post:
        return None
    job = InstagramJob(
        job_type=JobType.CREATE_COMMENT,
        account_id=post.account_id,
        post_id=post.id,
        payload_json={"text": text},
        status=JobStatus.PENDING,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def queue_reply(session: AsyncSession, comment_id: int, text: str) -> InstagramJob | None:
    comment = await get_comment(session, comment_id)
    if not comment:
        return None
    job = InstagramJob(
        job_type=JobType.REPLY_COMMENT,
        account_id=comment.account_id,
        post_id=comment.post_id,
        comment_id=comment.id,
        payload_json={"text": text},
        status=JobStatus.PENDING,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def list_outgoing_comment_jobs(
    session: AsyncSession, limit: int = 100
) -> list[InstagramJobResponse]:
    """Return the local outgoing-comment queue, including pending and failed work."""
    from app.repositories.jobs import list_jobs

    rows = await list_jobs(session, limit=limit)
    outgoing = [
        row for row in rows if row.job_type in (JobType.CREATE_COMMENT, JobType.REPLY_COMMENT)
    ]
    return [InstagramJobResponse.model_validate(row) for row in outgoing]
