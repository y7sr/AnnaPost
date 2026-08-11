"""Phase 2 API registration and contract tests."""

import pytest


@pytest.mark.asyncio
async def test_openapi_exposes_every_phase_2_business_path(async_client) -> None:
    response = await async_client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    expected = {
        "/api/v1/accounts": {"get", "post"},
        "/api/v1/accounts/{account_id}": {"get", "patch", "delete"},
        "/api/v1/posts": {"get", "post"},
        "/api/v1/posts/{post_id}": {"get", "patch", "delete"},
        "/api/v1/posts/{post_id}/schedule": {"post"},
        "/api/v1/posts/{post_id}/publish": {"post"},
        "/api/v1/posts/{post_id}/metrics": {"get"},
        "/api/v1/posts/{post_id}/comments": {"get", "post"},
        "/api/v1/comments/{comment_id}/reply": {"post"},
        "/api/v1/jobs": {"get"},
        "/api/v1/events": {"get"},
        "/api/v1/options": {"get"},
        "/api/v1/options/{key}": {"patch"},
    }
    assert {path: set(paths[path]) for path in expected} == expected


@pytest.mark.asyncio
async def test_business_routes_are_live(async_client) -> None:
    response = await async_client.post(
        "/api/v1/posts",
        json={
            "caption": "Example",
            "media_type": "image",
            "media_source_type": "url",
            "media_source": "https://example.com/image.jpg",
        },
    )
    assert response.status_code == 422
    assert "no enabled default account" in response.json()["detail"]
