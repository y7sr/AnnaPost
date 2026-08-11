"""Admin routes for Instagram comments."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.template_utils import render_template, render_template_with_status
from app.db.models.comment import InstagramComment
from app.db.session import get_db
from app.schemas.comment import InstagramCommentResponse
from app.services.comments import list_outgoing_comment_jobs, queue_reply
from app.services.comments import list_post_comments as read_comments

router = APIRouter()


@router.get("/")
async def list_comments_page(
    request: Request,
    post_id: int | None = None,
    session: AsyncSession = Depends(get_db),
):
    """Render comments list page."""
    if post_id:
        comments_list = await read_comments(session, post_id)
        comment_responses = comments_list.comments
    else:
        comments = await session.execute(
            select(InstagramComment).order_by(InstagramComment.created_at_remote.desc()).limit(100)
        )
        comment_responses = [
            InstagramCommentResponse.model_validate(comment) for comment in comments.scalars().all()
        ]

    outgoing_jobs = await list_outgoing_comment_jobs(session)
    outgoing = [
        {
            "id": job.id,
            "type": job.job_type.value,
            "post_id": job.post_id,
            "text": (job.payload_json or {}).get("text", ""),
            "status": "sent"
            if job.status.value == "completed"
            else "failed"
            if job.status.value in ("failed", "canceled")
            else "pending",
            "last_error": job.last_error,
        }
        for job in outgoing_jobs
    ]
    return render_template(
        "comments.html",
        request=request,
        comments=comment_responses,
        count=len(comment_responses),
        post_id_filter=post_id,
        showing_all=post_id is None,
        outgoing=outgoing,
    )


@router.get("/{comment_id}/")
async def get_comment_page(
    request: Request,
    comment_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Render comment detail page."""
    comment = await session.get(InstagramComment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    return render_template(
        "comment_detail.html",
        request=request,
        comment=InstagramCommentResponse.model_validate(comment),
    )


@router.get("/{comment_id}/reply/")
async def reply_comment_page(
    request: Request,
    comment_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Render reply form for a comment."""
    comment = await session.get(InstagramComment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    return render_template(
        "comment_reply.html",
        request=request,
        comment=InstagramCommentResponse.model_validate(comment),
    )


@router.post("/{comment_id}/reply/")
async def create_reply_page(
    request: Request,
    comment_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Create a reply to a comment."""
    comment = await session.get(InstagramComment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    form_data = await request.form()
    text = form_data.get("text", "").strip()

    if not text:
        return render_template_with_status(
            "comment_reply.html",
            status_code=400,
            request=request,
            comment=InstagramCommentResponse.model_validate(comment),
            error="Reply text is required",
        )

    job = await queue_reply(session, comment_id, text)
    if job is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    return RedirectResponse(url="/admin/comments/", status_code=303)
