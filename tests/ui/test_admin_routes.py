"""Smoke tests for admin UI routes.

These tests verify that each admin page renders 200 with expected key content.
Per phase 4 definition of done, an operator should be able to use only the browser.
"""

import pytest


@pytest.mark.asyncio
async def test_admin_dashboard_redirect(async_client):
    """Test that /admin/ redirects to /admin/accounts/."""
    response = await async_client.get("/admin/", follow_redirects=True)
    assert response.status_code == 200
    # The dashboard redirects to accounts
    assert "accounts" in response.text.lower()


@pytest.mark.asyncio
async def test_accounts_list_page(async_client):
    """Test that accounts list page renders with expected content."""
    response = await async_client.get("/admin/accounts/")
    assert response.status_code == 200
    assert "Accounts" in response.text
    assert "instagram" in response.text.lower() or "account" in response.text.lower()


@pytest.mark.asyncio
async def test_accounts_new_page(async_client):
    """Test that new account page renders."""
    response = await async_client.get("/admin/accounts/new/")
    assert response.status_code == 200
    assert "New Account" in response.text or "Create" in response.text


@pytest.mark.asyncio
async def test_posts_list_page(async_client):
    """Test that posts list page renders with expected content."""
    response = await async_client.get("/admin/posts/")
    assert response.status_code == 200
    assert "Posts" in response.text


@pytest.mark.asyncio
async def test_posts_new_page(async_client):
    """Test that new post page renders."""
    response = await async_client.get("/admin/posts/new/")
    assert response.status_code == 200
    assert "New Post" in response.text or "Create" in response.text


@pytest.mark.asyncio
async def test_jobs_list_page(async_client):
    """Test that jobs list page renders with expected content."""
    response = await async_client.get("/admin/jobs/")
    assert response.status_code == 200
    assert "Jobs" in response.text


@pytest.mark.asyncio
async def test_events_list_page(async_client):
    """Test that events list page renders with expected content."""
    response = await async_client.get("/admin/events/")
    assert response.status_code == 200
    assert "Events" in response.text


@pytest.mark.asyncio
async def test_metrics_list_page(async_client):
    """Test that metrics list page renders with expected content."""
    response = await async_client.get("/admin/metrics/")
    assert response.status_code == 200
    assert "Metrics" in response.text


@pytest.mark.asyncio
async def test_comments_list_page(async_client):
    """Test that comments list page renders with expected content."""
    response = await async_client.get("/admin/comments/")
    assert response.status_code == 200
    assert "Comments" in response.text


@pytest.mark.asyncio
async def test_posts_with_status_filter(async_client):
    """Test that posts page works with status filter."""
    for status_value in ["draft", "ready", "scheduled", "published", "failed"]:
        response = await async_client.get(f"/admin/posts/?status={status_value}")
        assert response.status_code == 200
        assert "Posts" in response.text


@pytest.mark.asyncio
async def test_jobs_with_type_filter(async_client):
    """Test that jobs page works with type filter."""
    for job_type in ["publish", "sync", "delete_post", "reply_comment"]:
        response = await async_client.get(f"/admin/jobs/?job_type={job_type}")
        assert response.status_code == 200
        assert "Jobs" in response.text


@pytest.mark.asyncio
async def test_jobs_with_status_filter(async_client):
    """Test that jobs page works with status filter."""
    for status_value in ["pending", "running", "completed", "failed", "canceled"]:
        response = await async_client.get(f"/admin/jobs/?status={status_value}")
        assert response.status_code == 200
        assert "Jobs" in response.text


@pytest.mark.asyncio
async def test_events_with_filters(async_client):
    """Test that events page works with account_id and post_id filters."""
    response = await async_client.get("/admin/events/?account_id=1")
    assert response.status_code == 200

    response = await async_client.get("/admin/events/?post_id=1")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_metrics_with_post_filter(async_client):
    """Test that metrics page works with post_id filter."""
    response = await async_client.get("/admin/metrics/?post_id=1")
    assert response.status_code == 200
    assert "Metrics" in response.text


@pytest.mark.asyncio
async def test_static_css_file(async_client):
    """Test that static CSS file is served."""
    response = await async_client.get("/admin/static/styles.css")
    assert response.status_code == 200
    assert "body" in response.text or "css" in response.text.lower()
