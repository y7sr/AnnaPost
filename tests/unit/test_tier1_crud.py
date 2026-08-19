"""Tier 1 CRUD implementation tests."""

from __future__ import annotations

import pytest

from app.db.models.post import PostStatus
from app.schemas.account import (
    InstagramAccountListResponse,
    InstagramAccountResponse,
)
from app.schemas.event import InstagramEventListResponse
from app.schemas.option import GlobalOptionListResponse
from app.schemas.post import (
    InstagramPostListResponse,
    InstagramPostResponse,
)

pytestmark = pytest.mark.usefixtures("mock_post_media_import")


@pytest.mark.asyncio
async def test_accounts_crud(async_client: object, db_session: object) -> None:
    """Test full Accounts CRUD flow."""
    # Create an account
    create_response = await async_client.post(
        "/api/v1/accounts",
        json={
            "name": "Test Account",
            "instagram_user_id": "123456789",
            "is_default": True,
            "enabled": True,
        },
    )
    assert create_response.status_code == 201
    account_data = create_response.json()
    assert account_data["name"] == "Test Account"
    assert account_data["is_default"] is True
    assert account_data["id"] is not None
    account_id = account_data["id"]

    # List accounts
    list_response = await async_client.get("/api/v1/accounts")
    assert list_response.status_code == 200
    list_data: InstagramAccountListResponse = InstagramAccountListResponse.model_validate(
        list_response.json()
    )
    assert list_data.count >= 1
    assert any(a.id == account_id for a in list_data.accounts)

    # Get single account
    get_response = await async_client.get(f"/api/v1/accounts/{account_id}")
    assert get_response.status_code == 200
    get_data: InstagramAccountResponse = InstagramAccountResponse.model_validate(
        get_response.json()
    )
    assert get_data.name == "Test Account"

    # Update account
    update_response = await async_client.patch(
        f"/api/v1/accounts/{account_id}",
        json={"name": "Updated Account"},
    )
    assert update_response.status_code == 200
    update_data: InstagramAccountResponse = InstagramAccountResponse.model_validate(
        update_response.json()
    )
    assert update_data.name == "Updated Account"


@pytest.mark.asyncio
async def test_accounts_default_invariant(async_client: object, db_session: object) -> None:
    """Test that only one account can be default."""
    # Create first default account
    response1 = await async_client.post(
        "/api/v1/accounts",
        json={"name": "Default 1", "is_default": True, "enabled": True},
    )
    assert response1.status_code == 201
    account1_id = response1.json()["id"]

    # Create second account marked as default - should demote the first
    response2 = await async_client.post(
        "/api/v1/accounts",
        json={"name": "Default 2", "is_default": True, "enabled": True},
    )
    assert response2.status_code == 201
    account2_id = response2.json()["id"]

    # Verify first account is no longer default
    get_response1 = await async_client.get(f"/api/v1/accounts/{account1_id}")
    assert get_response1.json()["is_default"] is False

    # Verify second account is default
    get_response2 = await async_client.get(f"/api/v1/accounts/{account2_id}")
    assert get_response2.json()["is_default"] is True


@pytest.mark.asyncio
async def test_posts_crud(async_client: object, db_session: object) -> None:
    """Test full Posts CRUD flow."""
    # Create an account first
    account_response = await async_client.post(
        "/api/v1/accounts",
        json={"name": "Test Account", "is_default": True, "enabled": True},
    )
    assert account_response.status_code == 201

    # Create a post
    create_response = await async_client.post(
        "/api/v1/posts",
        json={
            "caption": "Test post",
            "media_type": "image",
            "media_source_type": "url",
            "media_source": "https://example.com/image.jpg",
        },
    )
    assert create_response.status_code == 201
    post_data: InstagramPostResponse = InstagramPostResponse.model_validate(create_response.json())
    assert post_data.caption == "Test post"
    assert post_data.status == PostStatus.DRAFT
    assert post_data.idempotency_key is not None
    post_id = post_data.id

    # List posts
    list_response = await async_client.get("/api/v1/posts")
    assert list_response.status_code == 200
    list_data: InstagramPostListResponse = InstagramPostListResponse.model_validate(
        list_response.json()
    )
    assert list_data.count >= 1

    # Get single post
    get_response = await async_client.get(f"/api/v1/posts/{post_id}")
    assert get_response.status_code == 200
    get_data: InstagramPostResponse = InstagramPostResponse.model_validate(get_response.json())
    assert get_data.caption == "Test post"

    # Update post
    update_response = await async_client.patch(
        f"/api/v1/posts/{post_id}",
        json={"caption": "Updated caption"},
    )
    assert update_response.status_code == 200
    update_data: InstagramPostResponse = InstagramPostResponse.model_validate(
        update_response.json()
    )
    assert update_data.caption == "Updated caption"


@pytest.mark.asyncio
async def test_posts_default_account_fallback(async_client: object, db_session: object) -> None:
    """Test that posts fall back to default account when account_id is not provided."""
    # Create a default account
    account_response = await async_client.post(
        "/api/v1/accounts",
        json={"name": "Default Account", "is_default": True, "enabled": True},
    )
    assert account_response.status_code == 201
    account_id = account_response.json()["id"]

    # Create a post without account_id
    post_response = await async_client.post(
        "/api/v1/posts",
        json={
            "caption": "Test post",
            "media_type": "image",
            "media_source_type": "url",
            "media_source": "https://example.com/image.jpg",
        },
    )
    assert post_response.status_code == 201
    post_data: InstagramPostResponse = InstagramPostResponse.model_validate(post_response.json())
    assert post_data.account_id == account_id


@pytest.mark.asyncio
async def test_posts_no_default_account_error(async_client: object, db_session: object) -> None:
    """Test that creating a post without account_id fails when no default account exists."""
    # Create a non-default account
    await async_client.post(
        "/api/v1/accounts",
        json={"name": "Non-default Account", "is_default": False, "enabled": True},
    )

    # Try to create a post without account_id - should fail
    post_response = await async_client.post(
        "/api/v1/posts",
        json={
            "caption": "Test post",
            "media_type": "image",
            "media_source_type": "url",
            "media_source": "https://example.com/image.jpg",
        },
    )
    assert post_response.status_code == 422  # Validation error from ValueError


@pytest.mark.asyncio
async def test_posts_idempotency(async_client: object, db_session: object) -> None:
    """Test post creation with idempotency_key."""
    # Create an account
    await async_client.post(
        "/api/v1/accounts",
        json={"name": "Test Account", "is_default": True, "enabled": True},
    )

    # Create a post with idempotency_key
    idempotency_key = "unique-key-12345"
    response1 = await async_client.post(
        "/api/v1/posts",
        json={
            "caption": "Test post",
            "media_type": "image",
            "media_source_type": "url",
            "media_source": "https://example.com/image.jpg",
            "idempotency_key": idempotency_key,
        },
    )
    assert response1.status_code == 201
    post_id_1 = response1.json()["id"]

    # Create the same post again - should return the existing post
    response2 = await async_client.post(
        "/api/v1/posts",
        json={
            "caption": "Test post",
            "media_type": "image",
            "media_source_type": "url",
            "media_source": "https://example.com/image.jpg",
            "idempotency_key": idempotency_key,
        },
    )
    assert response2.status_code == 201
    post_id_2 = response2.json()["id"]
    assert post_id_1 == post_id_2


@pytest.mark.asyncio
async def test_posts_soft_delete(async_client: object, db_session: object) -> None:
    """Test soft deletion of posts."""
    # Create an account
    await async_client.post(
        "/api/v1/accounts",
        json={"name": "Test Account", "is_default": True, "enabled": True},
    )

    # Create a post
    post_response = await async_client.post(
        "/api/v1/posts",
        json={
            "caption": "Test post",
            "media_type": "image",
            "media_source_type": "url",
            "media_source": "https://example.com/image.jpg",
        },
    )
    assert post_response.status_code == 201
    post_id = post_response.json()["id"]

    # Soft delete the post
    delete_response = await async_client.delete(f"/api/v1/posts/{post_id}")
    assert delete_response.status_code == 202
    delete_data: InstagramPostResponse = InstagramPostResponse.model_validate(
        delete_response.json()
    )
    assert delete_data.soft_deleted is True
    assert delete_data.delete_requested_at is not None
    assert delete_data.status is PostStatus.CANCELED


@pytest.mark.asyncio
async def test_options_crud(async_client: object, db_session: object) -> None:
    """Test Options CRUD."""
    # Create an option
    create_response = await async_client.patch(
        "/api/v1/options/test_key",
        json={"value_json": {"setting": "value"}},
    )
    assert create_response.status_code == 200
    option_data = create_response.json()
    assert option_data["key"] == "test_key"
    assert option_data["value_json"] == {"setting": "value"}

    # List options
    list_response = await async_client.get("/api/v1/options")
    assert list_response.status_code == 200
    list_data: GlobalOptionListResponse = GlobalOptionListResponse.model_validate(
        list_response.json()
    )
    assert list_data.count >= 1
    assert any(o.key == "test_key" for o in list_data.options)

    # Update option
    update_response = await async_client.patch(
        "/api/v1/options/test_key",
        json={"value_json": {"setting": "updated_value"}},
    )
    assert update_response.status_code == 200
    update_data = update_response.json()
    assert update_data["value_json"] == {"setting": "updated_value"}


@pytest.mark.asyncio
async def test_events_list(async_client: object, db_session: object) -> None:
    """Test Events list endpoint."""
    # List events (should be empty initially)
    list_response = await async_client.get("/api/v1/events")
    assert list_response.status_code == 200
    list_data: InstagramEventListResponse = InstagramEventListResponse.model_validate(
        list_response.json()
    )
    assert list_data.count >= 0


@pytest.mark.asyncio
async def test_events_with_filters(async_client: object, db_session: object) -> None:
    """Test Events list with filters."""
    # List events with limit
    list_response = await async_client.get("/api/v1/events?limit=10")
    assert list_response.status_code == 200
    list_data: InstagramEventListResponse = InstagramEventListResponse.model_validate(
        list_response.json()
    )
    assert len(list_data.events) <= 10
