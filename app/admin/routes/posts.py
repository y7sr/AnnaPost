"""Admin routes for Instagram posts."""

from contextlib import suppress
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.template_utils import render_template, render_template_with_status
from app.db.models.post import PostStatus
from app.db.session import get_db
from app.schemas.post import (
    InstagramPostCreate,
    InstagramPostListResponse,
    InstagramPostUpdate,
)
from app.services.accounts import list_all_accounts
from app.services.posts import (
    cancel_existing_post,
    create_new_post,
    get_post,
    list_all_posts,
    queue_publish,
    request_post_deletion,
    schedule_existing_post,
    update_existing_post,
)

router = APIRouter()


def parse_admin_datetime(value: str) -> datetime:
    """Parse the UTC wall-clock value emitted by ``datetime-local``."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


@router.get("/")
async def list_posts_page(
    request: Request,
    status: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    """Render posts list page."""
    status_filter = status or "all"
    status_value = None
    if status_filter != "all":
        with suppress(ValueError):
            status_value = PostStatus(status_filter)

    posts_list: InstagramPostListResponse = await list_all_posts(
        session, status=status_value, limit=100
    )

    return render_template(
        "posts.html",
        request=request,
        posts=posts_list.posts,
        count=posts_list.count,
        status_filter=status_filter,
        status_values=[s.value for s in PostStatus],
    )


@router.get("/new/")
async def new_post_page(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Render new post form."""
    accounts_list = await list_all_accounts(session)
    return render_template(
        "post_new.html",
        request=request,
        post=None,
        accounts=accounts_list.accounts,
    )


@router.get("/{post_id}/")
async def get_post_page(
    request: Request,
    post_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Render post detail page."""
    post = await get_post(session, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    return render_template(
        "post_detail.html",
        request=request,
        post=post,
    )


@router.get("/{post_id}/edit/")
async def edit_post_page(
    request: Request,
    post_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Render post edit form."""
    post = await get_post(session, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    accounts_list = await list_all_accounts(session)
    return render_template(
        "post_edit.html",
        request=request,
        post=post,
        accounts=accounts_list.accounts,
    )


@router.post("/")
async def create_post_page(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Create a new post via form submission."""
    form_data = await request.form()

    # Parse account_id
    account_id_str = form_data.get("account_id", "").strip()
    account_id = int(account_id_str) if account_id_str else None

    media_type = form_data.get("media_type", "image").strip()
    media_source_type = form_data.get("media_source_type", "url").strip()
    media_source = form_data.get("media_source", "").strip()
    caption = form_data.get("caption", "").strip() or None
    scheduled_at_str = form_data.get("scheduled_at", "").strip()

    # Parse scheduled_at
    scheduled_at = None
    if scheduled_at_str:
        try:
            scheduled_at = parse_admin_datetime(scheduled_at_str)
        except ValueError:
            accounts_list = await list_all_accounts(session)
            return render_template_with_status(
                "post_new.html",
                status_code=400,
                request=request,
                post=None,
                accounts=accounts_list.accounts,
                error="Invalid scheduled time",
            )

    if not media_source:
        accounts_list = await list_all_accounts(session)
        return render_template_with_status(
            "post_new.html",
            status_code=400,
            request=request,
            post=None,
            accounts=accounts_list.accounts,
            error="Media source is required",
        )

    payload = InstagramPostCreate(
        account_id=account_id,
        media_type=media_type,
        media_source_type=media_source_type,
        media_source=media_source,
        media_payload_json=None,
        caption=caption,
        scheduled_at=scheduled_at,
        idempotency_key=None,
    )

    try:
        await create_new_post(session, payload)
    except ValueError as exc:
        accounts_list = await list_all_accounts(session)
        return render_template_with_status(
            "post_new.html",
            status_code=400,
            request=request,
            post=None,
            accounts=accounts_list.accounts,
            error=str(exc),
        )
    return RedirectResponse(url="/admin/posts/", status_code=303)


@router.post("/{post_id}/edit/")
async def update_post_page(
    request: Request,
    post_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Update a post via form submission."""
    post = await get_post(session, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    form_data = await request.form()

    media_source = form_data.get("media_source", "").strip()
    caption = form_data.get("caption", "").strip() or None

    if not media_source:
        accounts_list = await list_all_accounts(session)
        return render_template_with_status(
            "post_edit.html",
            status_code=400,
            request=request,
            post=post,
            accounts=accounts_list.accounts,
            error="Media source is required",
        )

    payload = InstagramPostUpdate(
        media_source=media_source,
        caption=caption,
    )

    updated_post = await update_existing_post(session, post_id, payload)
    if updated_post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    return RedirectResponse(url="/admin/posts/", status_code=303)


@router.post("/{post_id}/publish/")
async def publish_post_page(
    request: Request,
    post_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Publish a post immediately."""
    post = await get_post(session, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    job = await queue_publish(session, post_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    return RedirectResponse(url="/admin/posts/", status_code=303)


@router.post("/{post_id}/schedule/")
async def schedule_post_page(
    request: Request,
    post_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Schedule a post for future publication."""
    post = await get_post(session, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    form_data = await request.form()
    scheduled_at_str = form_data.get("scheduled_at", "").strip()

    if not scheduled_at_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scheduled time is required",
        )

    try:
        scheduled_at = parse_admin_datetime(scheduled_at_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid datetime format",
        ) from exc

    scheduled_post = await schedule_existing_post(session, post_id, scheduled_at)
    if scheduled_post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    return RedirectResponse(url="/admin/posts/", status_code=303)


@router.post("/{post_id}/cancel/")
async def cancel_post_page(
    request: Request,
    post_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Cancel an unpublished post through the post service."""
    try:
        canceled_post = await cancel_existing_post(session, post_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if canceled_post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    return RedirectResponse(url="/admin/posts/", status_code=303)


@router.post("/{post_id}/delete/")
async def delete_post_page(
    request: Request,
    post_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Request soft deletion of a post."""
    post = await get_post(session, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    try:
        deleted_post = await request_post_deletion(session, post_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if deleted_post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    return RedirectResponse(url="/admin/posts/", status_code=303)
