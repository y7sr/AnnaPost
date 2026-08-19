"""Publishing crash/rerun acceptance tests."""

from __future__ import annotations

from app.db.models.account import InstagramAccount
from app.db.models.post import InstagramPost, PostMediaSourceType, PostMediaType, PostStatus
from app.instagram.errors import InstagramTransientError
from app.instagram.schemas import InstagramContainer, InstagramMedia, InstagramPublishedMedia
from app.services.publishing import publish_claimed_post


class CrashAfterContainerClient:
    def __init__(self) -> None:
        self.created = 0
        self.fail_publish = True
        self.fail_get_media = False
        self.access_tokens: list[str] = []

    async def create_image_container(self, **kwargs: str) -> InstagramContainer:
        self.access_tokens.append(kwargs["access_token"])
        self.created += 1
        return InstagramContainer(id="container-1")

    async def publish_container(self, **kwargs: str) -> InstagramPublishedMedia:
        self.access_tokens.append(kwargs["access_token"])
        if self.fail_publish:
            raise InstagramTransientError("simulated crash")
        return InstagramPublishedMedia(id="media-1")

    async def get_media(self, **kwargs: str) -> InstagramMedia:
        self.access_tokens.append(kwargs["access_token"])
        if self.fail_get_media:
            raise InstagramTransientError("simulated timeout on get_media")
        return InstagramMedia(id="media-1", permalink="https://ig/p", caption="test caption")


class TimeoutAfterPublishClient:
    """Client that times out on get_media after successful publish_container."""

    def __init__(self) -> None:
        self.access_tokens: list[str] = []

    async def create_image_container(self, **kwargs: str) -> InstagramContainer:
        self.access_tokens.append(kwargs["access_token"])
        return InstagramContainer(id="container-1")

    async def publish_container(self, **kwargs: str) -> InstagramPublishedMedia:
        self.access_tokens.append(kwargs["access_token"])
        return InstagramPublishedMedia(id="media-1")

    async def get_media(self, **kwargs: str) -> InstagramMedia:
        self.access_tokens.append(kwargs["access_token"])
        raise InstagramTransientError("timeout after media_publish")


async def test_rerun_reuses_persisted_container_after_failure(db_session, monkeypatch) -> None:
    account = InstagramAccount(
        name="primary",
        is_default=True,
        instagram_user_id="user",
        access_token_ref="env:TEST_INSTAGRAM_TOKEN",
    )
    post = InstagramPost(
        account=account,
        media_type=PostMediaType.IMAGE,
        media_source_type=PostMediaSourceType.URL,
        media_source="https://example.test/image.jpg",
        status=PostStatus.PUBLISHING,
    )
    db_session.add_all([account, post])
    await db_session.commit()
    await db_session.refresh(post)
    client = CrashAfterContainerClient()

    monkeypatch.setenv("TEST_INSTAGRAM_TOKEN", "test-token")

    assert not await publish_claimed_post(db_session, post.id, client)
    await db_session.refresh(post)
    assert post.instagram_container_id == "container-1"
    assert client.created == 1
    assert client.access_tokens == ["test-token", "test-token"]

    post.status = PostStatus.PUBLISHING
    client.fail_publish = False
    await db_session.commit()
    assert await publish_claimed_post(db_session, post.id, client)
    await db_session.refresh(post)
    assert post.status is PostStatus.PUBLISHED
    assert post.instagram_media_id == "media-1"
    assert client.created == 1
    assert client.access_tokens == ["test-token"] * 4


async def test_ambiguous_timeout_after_media_publish(db_session, monkeypatch, caplog) -> None:
    """Test explicit handling for ambiguous timeouts after media_publish.

    When publish_container succeeds but get_media fails with a transient error
    (e.g., timeout), the publish should still be considered successful since
    we have the media_id. The post should be marked as PUBLISHED with sync_pending
    status, and the metadata can be synced later.
    """
    account = InstagramAccount(
        name="primary",
        is_default=True,
        instagram_user_id="user",
        access_token_ref="env:TEST_INSTAGRAM_TOKEN",
    )
    post = InstagramPost(
        account=account,
        media_type=PostMediaType.IMAGE,
        media_source_type=PostMediaSourceType.URL,
        media_source="https://example.test/image.jpg",
        status=PostStatus.PUBLISHING,
    )
    db_session.add_all([account, post])
    await db_session.commit()
    await db_session.refresh(post)

    client = TimeoutAfterPublishClient()
    monkeypatch.setenv("TEST_INSTAGRAM_TOKEN", "test-token")

    # publish_claimed_post should succeed despite get_media timeout
    assert await publish_claimed_post(db_session, post.id, client)

    await db_session.refresh(post)
    # Post should be marked as PUBLISHED (not FAILED)
    assert post.status is PostStatus.PUBLISHED
    # We should have the media_id from publish_container
    assert post.instagram_media_id == "media-1"
    assert post.instagram_container_id == "container-1"
    # But permalink should be None due to get_media timeout
    assert post.instagram_permalink is None
    # Caption should be None (we couldn't fetch it)
    assert post.remote_caption_last_known is None
    # Caption sync status should be sync_pending
    assert post.caption_sync_status == "sync_pending"
    # Error should be None (we didn't fail the publish)
    assert post.last_error is None

    # Check that the warning was logged
    assert any(
        "Ambiguous timeout after media_publish" in record.message for record in caplog.records
    )
