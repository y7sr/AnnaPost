"""Post endpoint contracts."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.post import PostStatus
from app.db.session import get_db
from app.schemas.job import InstagramJobResponse
from app.schemas.post import (
    InstagramPostCreate,
    InstagramPostListResponse,
    InstagramPostPublish,
    InstagramPostResponse,
    InstagramPostSchedule,
    InstagramPostUpdate,
)
from app.services.posts import (
    create_new_post,
    list_all_posts,
    queue_publish,
    schedule_existing_post,
    update_existing_post,
)
from app.services.posts import (
    get_post as get_post_service,
)
from app.services.posts import (
    request_post_deletion as request_post_deletion_service,
)

router = APIRouter(prefix="/posts")


@router.get("", response_model=InstagramPostListResponse)
async def list_posts(
    account_id: int | None = Query(None),
    status: PostStatus | None = Query(None),
    limit: int | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> InstagramPostListResponse:
    """List posts."""
    return await list_all_posts(
        session,
        account_id=account_id,
        status=status,
        limit=limit,
    )


@router.post("", response_model=InstagramPostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: InstagramPostCreate,
    session: AsyncSession = Depends(get_db),
) -> InstagramPostResponse:
    """Create a desired post from the external-producer contract."""
    try:
        return await create_new_post(session, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get("/{post_id}", response_model=InstagramPostResponse)
async def get_post(
    post_id: int,
    session: AsyncSession = Depends(get_db),
) -> InstagramPostResponse:
    """Get one post."""
    post = await get_post_service(session, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@router.patch("/{post_id}", response_model=InstagramPostResponse)
async def update_post(
    post_id: int,
    payload: InstagramPostUpdate,
    session: AsyncSession = Depends(get_db),
) -> InstagramPostResponse:
    """Update editable post metadata."""
    post = await update_existing_post(session, post_id, payload)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@router.post("/{post_id}/schedule", response_model=InstagramPostResponse)
async def schedule_post(
    post_id: int, payload: InstagramPostSchedule, session: AsyncSession = Depends(get_db)
) -> InstagramPostResponse:
    """Set a future publication time."""
    try:
        post = await schedule_existing_post(session, post_id, payload.scheduled_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@router.post(
    "/{post_id}/publish", response_model=InstagramJobResponse, status_code=status.HTTP_202_ACCEPTED
)
async def publish_post(
    post_id: int, payload: InstagramPostPublish, session: AsyncSession = Depends(get_db)
) -> InstagramJobResponse:
    """Queue immediate publication without calling Instagram in the request."""
    del payload
    try:
        job = await queue_publish(session, post_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if job is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return InstagramJobResponse.model_validate(job)


@router.delete(
    "/{post_id}", response_model=InstagramPostResponse, status_code=status.HTTP_202_ACCEPTED
)
async def request_post_deletion(
    post_id: int,
    session: AsyncSession = Depends(get_db),
) -> InstagramPostResponse:
    """Request soft deletion and later remote reconciliation."""
    try:
        post = await request_post_deletion_service(session, post_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post
