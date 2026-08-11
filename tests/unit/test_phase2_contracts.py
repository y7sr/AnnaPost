"""Focused acceptance tests for Phase 2 architecture contracts."""

from __future__ import annotations

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models.metrics import InstagramPostMetric
from app.db.models.post import PostMediaSourceType
from app.db.session import apply_sqlite_pragmas
from app.instagram.client import InstagramClient
from app.instagram.errors import (
    InstagramAuthenticationError,
    InstagramRateLimitError,
    InstagramTransientError,
    InstagramValidationError,
)
from app.instagram.metrics import normalize_post_metrics
from app.schemas.post import InstagramPostCreate
from app.services.media import MediaResolutionError, UrlMediaResolver
from app.services.retry_policy import retry_delay_seconds


def test_external_producer_minimal_post_payload_is_stable() -> None:
    post = InstagramPostCreate.model_validate(
        {
            "caption": "Example",
            "media_type": "image",
            "media_source_type": "url",
            "media_source": "https://example.com/image.jpg",
        }
    )
    assert post.account_id is None
    assert post.idempotency_key is None


def test_external_producer_cannot_set_post_lifecycle_status() -> None:
    with pytest.raises(ValueError, match="status"):
        InstagramPostCreate.model_validate(
            {
                "media_type": "image",
                "media_source_type": "url",
                "media_source": "https://example.com/image.jpg",
                "status": "published",
            }
        )


def test_carousel_payload_shape_is_normalized() -> None:
    post = InstagramPostCreate.model_validate(
        {
            "media_type": "carousel",
            "media_source_type": "url",
            "media_source": "https://example.com/cover.jpg",
            "media_payload_json": {
                "items": [
                    {
                        "media_type": "image",
                        "media_source_type": "url",
                        "media_source": "https://example.com/one.jpg",
                    },
                    {
                        "media_type": "reel",
                        "media_source_type": "url",
                        "media_source": "https://example.com/two.mp4",
                    },
                ]
            },
        }
    )
    assert post.media_payload_json == {
        "items": [
            {
                "media_type": "image",
                "media_source_type": "url",
                "media_source": "https://example.com/one.jpg",
            },
            {
                "media_type": "reel",
                "media_source_type": "url",
                "media_source": "https://example.com/two.mp4",
            },
        ]
    }


def test_normalization_preserves_zero_and_missing_as_distinct_values() -> None:
    normalized = normalize_post_metrics(
        {
            "data": [
                {"name": "reach", "values": [{"value": 0}]},
                {"name": "saved", "values": []},
            ]
        }
    )
    assert normalized.reach == 0
    assert normalized.saved is None
    assert normalized.plays is None


def test_metric_columns_have_no_python_or_server_default() -> None:
    numeric_columns = (
        "views",
        "reach",
        "plays",
        "avg_watch_time_ms",
        "total_watch_time_ms",
        "likes",
        "comments",
        "saved",
        "shares",
        "total_interactions",
        "profile_activity",
        "follows",
    )
    for name in numeric_columns:
        column = InstagramPostMetric.__table__.c[name]
        assert column.default is None
        assert column.server_default is None


def test_retry_policy_retries_only_transient_errors() -> None:
    assert retry_delay_seconds(InstagramTransientError("timeout"), attempt=2) == 300
    assert (
        retry_delay_seconds(InstagramRateLimitError("slow down", retry_after_seconds=42), attempt=1)
        == 42
    )
    assert retry_delay_seconds(InstagramAuthenticationError("expired"), attempt=1) is None
    assert retry_delay_seconds(InstagramValidationError("bad media"), attempt=1) is None


async def test_url_resolver_accepts_only_existing_http_urls() -> None:
    resolver = UrlMediaResolver()
    assert (
        await resolver.resolve(
            source_type=PostMediaSourceType.URL,
            source="https://example.com/image.jpg",
        )
        == "https://example.com/image.jpg"
    )
    with pytest.raises(MediaResolutionError):
        await resolver.resolve(source_type=PostMediaSourceType.URL, source="file:///tmp/image.jpg")
    with pytest.raises(MediaResolutionError):
        await resolver.resolve(source_type=PostMediaSourceType.LOCAL_FILE, source="image.jpg")


async def test_instagram_client_is_implemented_in_phase_3() -> None:
    import httpx
    import respx

    from app.core.config import settings

    with respx.mock:
        respx.get(
            f"{settings.instagram_graph_base_url}/{settings.ig_graph_api_version}/media"
        ).mock(return_value=httpx.Response(200, json={"id": "media"}))
        assert (
            await InstagramClient().get_media(access_token="not-a-real-token", media_id="media")
        ).id == "media"


async def test_sqlite_pragmas_execute_on_connection_lifecycle(temp_db_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{temp_db_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def set_pragmas(dbapi_connection, _connection_record) -> None:
        apply_sqlite_pragmas(dbapi_connection)

    async with engine.connect() as connection:
        assert (await connection.execute(text("PRAGMA foreign_keys"))).scalar_one() == 1
        assert (await connection.execute(text("PRAGMA journal_mode"))).scalar_one() == "wal"
        assert (await connection.execute(text("PRAGMA busy_timeout"))).scalar_one() == 5000
    await engine.dispose()
