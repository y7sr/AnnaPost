"""Health endpoint tests."""

import pytest


@pytest.mark.asyncio
async def test_health_endpoint(async_client) -> None:
    """Test that GET /health returns 200 and {"status": "ok"}."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
