"""Vend1r bridge runner tests; no Instagram Graph calls are allowed."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from httpx import Response
from sqlalchemy import select

from app.core.config import settings
from app.db.models.account import InstagramAccount
from app.db.models.job import InstagramJob
from app.db.models.post import InstagramPost, PostMediaSourceType, PostStatus
from app.services.vend1r_bridge import synchronize_vend1r_posts


@pytest.mark.asyncio
@respx.mock
async def test_do_not_publish_is_skipped_without_creating_post_or_job(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "annapost_bridge_token", "test-bridge-token")
    monkeypatch.setattr(settings, "vend1r_bridge_base_url", "https://vend1r.test")
    monkeypatch.setattr(settings, "vend1r_bridge_workspace_id", "frdprfct")

    respx.get("https://vend1r.test/api/v1/annapost-bridge/posts?workspace_id=frdprfct").mock(
        return_value=Response(
            200,
            json={
                "posts": [
                    {
                        "internal_post_id": "vend1r:20:fragment:1",
                        "status": "do_not_publish",
                        "caption": "Must not be imported",
                        "media_url": "https://vend1r.test/storage/20.jpg",
                    }
                ]
            },
        )
    )

    report = await synchronize_vend1r_posts(db_session)

    assert report == {
        "fetched": 1,
        "skipped": 1,
        "created": 0,
        "updated": 0,
        "published_queued": 0,
        "deleted_requested": 0,
        "reported": 0,
    }
    assert (await db_session.execute(select(InstagramPost))).scalars().all() == []
    assert (await db_session.execute(select(InstagramJob))).scalars().all() == []


@pytest.mark.asyncio
@respx.mock
async def test_draft_is_imported_with_durable_media_without_publish_job(
    db_session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "annapost_bridge_token", "test-bridge-token")
    monkeypatch.setattr(settings, "vend1r_bridge_base_url", "https://vend1r.test")
    monkeypatch.setattr(settings, "vend1r_bridge_workspace_id", "frdprfct")
    monkeypatch.setattr(settings, "media_storage_dir", tmp_path / "media")
    db_session.add(
        InstagramAccount(
            name="default",
            is_default=True,
            enabled=True,
            instagram_user_id="test-user",
            access_token_ref="env:TEST_TOKEN",
        )
    )
    await db_session.commit()

    respx.get("https://vend1r.test/api/v1/annapost-bridge/posts?workspace_id=frdprfct").mock(
        return_value=Response(
            200,
            json={
                "posts": [
                    {
                        "internal_post_id": "vend1r:20:fragment:1",
                        "status": "draft",
                        "caption": "A durable draft",
                        "media_url": "https://vend1r.test/storage/20.jpg",
                    }
                ]
            },
        )
    )
    respx.put(
        "https://vend1r.test/api/v1/annapost-bridge/posts/vend1r:20:fragment:1?workspace_id=frdprfct"
    ).mock(return_value=Response(200, json={"status": "draft"}))
    media = respx.get("https://vend1r.test/storage/20.jpg").mock(
        return_value=Response(200, headers={"content-type": "image/jpeg"}, content=b"jpeg")
    )

    report = await synchronize_vend1r_posts(db_session)

    post = (await db_session.execute(select(InstagramPost))).scalar_one()
    jobs = (await db_session.execute(select(InstagramJob))).scalars().all()
    assert report["created"] == 1
    assert report["published_queued"] == 0
    assert post.status is PostStatus.DRAFT
    assert post.media_source_type is PostMediaSourceType.LOCAL_FILE
    assert (tmp_path / "media" / post.media_source).read_bytes() == b"jpeg"
    assert jobs == []
    assert media.called
