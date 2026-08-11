"""Comment endpoint contracts."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.comment import (
    CommentCreateRequest,
    InstagramCommentListResponse,
    ReplyCreateRequest,
)
from app.schemas.job import InstagramJobResponse
from app.services.comments import list_post_comments as read_comments
from app.services.comments import queue_comment, queue_reply

router = APIRouter()


@router.get("/posts/{post_id}/comments", response_model=InstagramCommentListResponse)
async def list_post_comments(
    post_id: int, session: AsyncSession = Depends(get_db)
) -> InstagramCommentListResponse:
    """List comments imported for one post."""
    return await read_comments(session, post_id)


@router.post(
    "/posts/{post_id}/comments",
    response_model=InstagramJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_post_comment(
    post_id: int, payload: CommentCreateRequest, session: AsyncSession = Depends(get_db)
) -> InstagramJobResponse:
    """Queue a top-level outgoing comment."""
    job = await queue_comment(session, post_id, payload.text)
    if not job:
        raise HTTPException(status_code=404, detail="Post not found")
    return InstagramJobResponse.model_validate(job)


@router.post(
    "/comments/{comment_id}/reply",
    response_model=InstagramJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reply_to_comment(
    comment_id: int, payload: ReplyCreateRequest, session: AsyncSession = Depends(get_db)
) -> InstagramJobResponse:
    """Queue a reply to an imported or outgoing comment."""
    job = await queue_reply(session, comment_id, payload.text)
    if not job:
        raise HTTPException(status_code=404, detail="Comment not found")
    return InstagramJobResponse.model_validate(job)
