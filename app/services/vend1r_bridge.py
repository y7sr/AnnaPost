"""Idempotent Vend1r polling and status reconciliation for AnnaPost."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.post import PostMediaSourceType, PostMediaType, PostStatus
from app.repositories.posts import get_post_by_idempotency_key
from app.schemas.post import InstagramPostCreate, InstagramPostUpdate
from app.services.posts import (
    create_new_post,
    queue_publish,
    request_post_deletion,
    update_existing_post,
)


class Vend1rBridgeError(RuntimeError):
    """The bridge cannot safely synchronize without its shared token."""


def _headers() -> dict[str, str]:
    token = settings.annapost_bridge_token
    if not token:
        raise Vend1rBridgeError("ANNAPOST_BRIDGE_TOKEN is not configured")
    return {"X-AnnaPost-Bridge-Token": token}


async def _write_vend1r(client: httpx.AsyncClient, internal_post_id: str, post: Any) -> None:
    payload = {"status": post.status.value}
    if post.instagram_permalink:
        payload["instagram_post_url"] = post.instagram_permalink
    response = await client.put(f"/api/v1/annapost-bridge/posts/{internal_post_id}", json=payload)
    response.raise_for_status()


async def synchronize_vend1r_posts(session: AsyncSession) -> dict[str, int]:
    """Poll Vend1r, create/update desired posts, then report AnnaPost state."""
    headers = _headers()
    report = {"created": 0, "updated": 0, "published_queued": 0, "deleted_requested": 0, "reported": 0}
    async with httpx.AsyncClient(base_url=settings.vend1r_bridge_base_url.rstrip("/"), headers=headers, timeout=30.0) as client:
        response = await client.get("/api/v1/annapost-bridge/posts")
        response.raise_for_status()
        for source in response.json().get("posts", []):
            internal_post_id = source["internal_post_id"]
            desired_status = source["status"]
            post = await get_post_by_idempotency_key(session, internal_post_id)
            if post is None:
                post = await create_new_post(session, InstagramPostCreate(
                    media_type=PostMediaType.IMAGE,
                    media_source_type=PostMediaSourceType.URL,
                    media_source=source["media_url"],
                    caption=source["caption"],
                    idempotency_key=internal_post_id,
                ))
                report["created"] += 1
                post = await get_post_by_idempotency_key(session, internal_post_id)
            assert post is not None

            if desired_status in {"draft", "ready", "scheduled"} and post.status in {PostStatus.DRAFT, PostStatus.READY, PostStatus.SCHEDULED}:
                updated = await update_existing_post(session, post.id, InstagramPostUpdate(caption=source["caption"]))
                post = await get_post_by_idempotency_key(session, internal_post_id)
                report["updated"] += int(updated is not None)
            if desired_status == "ready" and post.status in {PostStatus.DRAFT, PostStatus.FAILED}:
                await queue_publish(session, post.id)
                post = await get_post_by_idempotency_key(session, internal_post_id)
                report["published_queued"] += 1
            elif desired_status == "deleted" and post.status not in {PostStatus.DELETED, PostStatus.CANCELED, PostStatus.DELETE_REQUESTED}:
                await request_post_deletion(session, post.id)
                post = await get_post_by_idempotency_key(session, internal_post_id)
                report["deleted_requested"] += 1
            await _write_vend1r(client, internal_post_id, post)
            report["reported"] += 1
    return report
