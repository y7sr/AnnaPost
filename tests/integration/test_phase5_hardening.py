"""Phase 5 acceptance tests: safe failures, API validation, and logging."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx

from app.core.config import settings
from app.core.logging import log_runner_execution
from app.db.models.account import InstagramAccount
from app.db.models.job import InstagramJob, JobStatus, JobType
from app.db.models.post import InstagramPost, PostMediaSourceType, PostMediaType, PostStatus
from app.instagram.client import InstagramClient
from app.instagram.errors import InstagramAuthenticationError, InstagramError
from app.instagram.schemas import (
    InstagramCommentsPage,
    InstagramContainer,
    InstagramCreatedComment,
    InstagramMedia,
    InstagramPublishedMedia,
    InstagramRemoteComment,
)
from app.schemas.account import InstagramAccountCreate
from app.schemas.post import InstagramPostCreate
from app.services.accounts import create_new_account
from app.services.actions import execute_action
from app.services.comments import queue_comment
from app.services.posts import create_new_post, request_post_deletion
from app.services.publishing import publish_claimed_post
from app.services.sync import sync_post

pytestmark = pytest.mark.usefixtures("mock_post_media_import")


class EndToEndClient:
    async def create_image_container(self, **_: str) -> InstagramContainer:
        return InstagramContainer(id="container-1")

    async def publish_container(self, **_: str) -> InstagramPublishedMedia:
        return InstagramPublishedMedia(id="media-1")

    async def get_media(self, **_: str) -> InstagramMedia:
        return InstagramMedia(id="media-1", permalink="https://instagram.test/p/media-1")

    async def get_media_insights(self, **_: str) -> dict:
        return {"data": [{"name": "impressions", "values": [{"value": 7}]}]}

    async def get_comments(self, **_: str) -> InstagramCommentsPage:
        return InstagramCommentsPage(
            comments=[InstagramRemoteComment(id="remote-comment", text="hello")], next_cursor=None
        )

    async def create_comment(self, **_: str) -> InstagramCreatedComment:
        return InstagramCreatedComment(id="outgoing-comment")

    async def delete_media(self, **_: str) -> None:
        return None


class TransactionBoundaryClient:
    def __init__(self, session) -> None:
        self.session = session

    async def create_comment(self, **_: str) -> InstagramCreatedComment:
        assert not self.session.in_transaction()
        return InstagramCreatedComment(id="outgoing-comment")


async def test_v1_flow_uses_only_the_mocked_instagram_boundary(db_session, monkeypatch) -> None:
    """Exercise the Definition-of-Done lifecycle without any network access."""

    class FakeMediaServer:
        origin_url = "http://127.0.0.1:9999"
        route = "/test-media.jpg"

        def __init__(self, *_: object) -> None:
            pass

        def __enter__(self) -> FakeMediaServer:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    class FakeTunnel:
        def __init__(self, *_: object) -> None:
            pass

        async def start(self) -> str:
            return "https://media.test"

        async def stop(self) -> None:
            pass

    monkeypatch.setattr("app.services.publishing.SingleFileServer", FakeMediaServer)
    monkeypatch.setattr("app.services.publishing.NgrokTunnel", FakeTunnel)

    primary = await create_new_account(
        db_session,
        InstagramAccountCreate(
            name="primary",
            is_default=True,
            instagram_user_id="user-1",
            access_token_ref="env:TOKEN_1",
        ),
    )
    secondary = await create_new_account(
        db_session,
        InstagramAccountCreate(
            name="secondary", instagram_user_id="user-2", access_token_ref="env:TOKEN_2"
        ),
    )
    post = await create_new_post(
        db_session,
        InstagramPostCreate(
            media_type="image",
            media_source_type="url",
            media_source="https://example.test/image.jpg",
        ),
    )
    other_post = await create_new_post(
        db_session,
        InstagramPostCreate(
            account_id=secondary.id,
            media_type="image",
            media_source_type="url",
            media_source="https://example.test/other.jpg",
        ),
    )
    assert post.account_id == primary.id
    assert other_post.account_id == secondary.id

    persisted = await db_session.get(InstagramPost, post.id)
    assert persisted is not None
    persisted.status = PostStatus.PUBLISHING
    publish_job = InstagramJob(
        job_type=JobType.PUBLISH,
        account_id=primary.id,
        post_id=post.id,
        status=JobStatus.RUNNING,
        attempts=1,
    )
    db_session.add(publish_job)
    await db_session.commit()
    client = EndToEndClient()
    assert await publish_claimed_post(db_session, post.id, client, publish_job.id)
    await db_session.refresh(persisted)
    assert persisted.status is PostStatus.PUBLISHED
    assert persisted.instagram_media_id == "media-1"

    assert await sync_post(db_session, post.id, client)
    assert await sync_post(db_session, post.id, client)  # imports the same comment only once
    comment_job = await queue_comment(db_session, post.id, "Thanks")
    assert comment_job is not None
    comment_job.status = JobStatus.RUNNING
    comment_job.attempts = 1
    await db_session.commit()
    assert await execute_action(db_session, comment_job.id, client)

    deleted = await request_post_deletion(db_session, post.id)
    assert deleted is not None and deleted.soft_deleted
    delete_job = (
        await db_session.execute(
            __import__("sqlalchemy")
            .select(InstagramJob)
            .where(InstagramJob.job_type == JobType.DELETE_POST)
        )
    ).scalar_one()
    delete_job.status = JobStatus.RUNNING
    delete_job.attempts = 1
    await db_session.commit()
    assert await execute_action(db_session, delete_job.id, client)
    await db_session.refresh(persisted)
    assert persisted.status is PostStatus.DELETED


async def test_comment_action_ends_the_database_transaction_before_graph(db_session) -> None:
    account = await create_new_account(
        db_session,
        InstagramAccountCreate(
            name="primary",
            is_default=True,
            instagram_user_id="user-1",
            access_token_ref="env:TOKEN_1",
        ),
    )
    post = await create_new_post(
        db_session,
        InstagramPostCreate(
            account_id=account.id,
            media_type="image",
            media_source_type="url",
            media_source="https://example.test/image.jpg",
        ),
    )
    job = await queue_comment(db_session, post.id, "Thanks")
    assert job is not None
    job.status, job.attempts = JobStatus.RUNNING, 1
    await db_session.commit()

    assert await execute_action(db_session, job.id, TransactionBoundaryClient(db_session))


async def test_malformed_and_expired_instagram_responses_are_typed_and_safe() -> None:
    """Graph boundary never lets malformed or expired-token responses escape raw."""
    base = f"{settings.instagram_graph_base_url}/{settings.ig_graph_api_version}"
    async with httpx.AsyncClient() as http_client:
        client = InstagramClient(http_client)
        with respx.mock:
            respx.get(f"{base}/malformed").mock(
                return_value=httpx.Response(
                    200, content=b"not-json", headers={"content-type": "text/plain"}
                )
            )
            with pytest.raises(InstagramError, match="invalid JSON"):
                await client.get_media(access_token="secret-token", media_id="malformed")

            respx.get(f"{base}/expired").mock(
                return_value=httpx.Response(
                    400,
                    json={"error": {"code": 190, "message": "Token expired"}},
                )
            )
            with pytest.raises(InstagramAuthenticationError):
                await client.get_media(access_token="secret-token", media_id="expired")


async def test_permanent_publish_configuration_failure_finishes_job(db_session) -> None:
    """A missing credential becomes a terminal job failure, never a stuck retry."""
    account = InstagramAccount(name="missing-token", is_default=True, instagram_user_id="user")
    post = InstagramPost(
        account=account,
        media_type=PostMediaType.IMAGE,
        media_source_type=PostMediaSourceType.URL,
        media_source="https://example.test/image.jpg",
        status=PostStatus.PUBLISHING,
    )
    job = InstagramJob(
        job_type=JobType.PUBLISH,
        account=account,
        post=post,
        status=JobStatus.RUNNING,
        attempts=1,
    )
    db_session.add_all([account, post, job])
    await db_session.commit()

    assert not await publish_claimed_post(db_session, post.id, job_id=job.id)
    await db_session.refresh(post)
    await db_session.refresh(job)
    assert job.status is JobStatus.FAILED
    assert job.run_after is None
    assert post.status is PostStatus.FAILED


async def test_api_validation_is_a_clean_4xx_and_never_discloses_tokens(async_client) -> None:
    response = await async_client.post(
        "/api/v1/accounts",
        json={"name": "safe", "access_token_ref": "env:SECRET_TOKEN"},
    )
    assert response.status_code == 201
    assert "access_token_ref" not in response.json()

    invalid = await async_client.post(
        "/api/v1/posts",
        json={
            "media_type": "image",
            "media_source_type": "url",
            "media_source": "file:///tmp/nope",
        },
    )
    assert invalid.status_code == 422
    assert "SECRET_TOKEN" not in invalid.text


def test_structured_runner_logs_have_the_required_safe_fields(caplog) -> None:
    caplog.set_level(logging.INFO)
    log_runner_execution(
        logging.getLogger("test.runner"),
        runner="publish",
        operation="publish",
        result="success",
        duration=0.125,
        job_id=1,
        post_id=2,
        account_id=3,
        instagram_media_id="media-4",
        attempt=1,
    )
    fields = json.loads(caplog.records[-1].message.removeprefix("runner_execution "))
    assert set(fields) == {
        "runner",
        "job_id",
        "post_id",
        "account_id",
        "instagram_media_id",
        "operation",
        "attempt",
        "duration",
        "result",
        "error_type",
    }
    assert "token" not in caplog.text.lower()
