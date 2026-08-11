"""Synchronize one published post into append-only local observations."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.credentials import resolve_access_token
from app.db.models.account import InstagramAccount
from app.db.models.event import EventType
from app.instagram.client import InstagramClient
from app.instagram.metrics import normalize_post_metrics
from app.repositories.comments import upsert_comment
from app.repositories.metrics import create_snapshot
from app.services.events import write_event
from app.services.options import get_option_value


def next_sync_time(
    published_at: datetime, now: datetime, intervals: dict[str, int] | None = None
) -> datetime:
    intervals = intervals or {"under_24h": 3600, "one_to_seven_days": 21600, "over_7_days": 86400}
    age = now - published_at.replace(tzinfo=published_at.tzinfo or UTC)
    seconds = (
        intervals["under_24h"]
        if age < timedelta(days=1)
        else intervals["one_to_seven_days"]
        if age < timedelta(days=7)
        else intervals["over_7_days"]
    )
    return now + timedelta(seconds=seconds)


async def sync_post(
    session: AsyncSession, post_id: int, client: InstagramClient | None = None
) -> bool:
    from app.repositories.posts import get_post_by_id

    post = await get_post_by_id(session, post_id)
    if not post or not post.instagram_media_id:
        return False
    account = await session.get(InstagramAccount, post.account_id)
    if not account or not account.access_token_ref:
        return False
    try:
        access_token = resolve_access_token(account.access_token_ref)
    except ValueError:
        return False
    api, now = client or InstagramClient(), datetime.now(UTC)
    await write_event(
        session, event_type=EventType.SYNC_STARTED, account_id=post.account_id, post_id=post.id
    )
    try:
        metrics = normalize_post_metrics(
            await api.get_media_insights(
                access_token=access_token, media_id=post.instagram_media_id
            )
        )
        snapshot = await create_snapshot(session, post_id=post.id, **metrics.model_dump())
        await write_event(
            session,
            event_type=EventType.METRIC_SNAPSHOT_CREATED,
            account_id=post.account_id,
            post_id=post.id,
            payload_json={"metric_id": snapshot.id},
        )
        page = await api.get_comments(
            access_token=access_token, media_id=post.instagram_media_id
        )
        for remote in page.comments:
            await upsert_comment(
                session,
                account_id=post.account_id,
                post_id=post.id,
                instagram_comment_id=remote.id,
                parent_instagram_comment_id=remote.parent_id,
                username=remote.username,
                text=remote.text,
                created_at_remote=remote.timestamp,
                like_count_if_available=remote.like_count,
                is_reply=bool(remote.parent_id),
                raw_json=remote.raw,
            )
        configured_intervals = await get_option_value(session, "default_sync_intervals")
        intervals = configured_intervals if isinstance(configured_intervals, dict) else None
        post.last_synced_at, post.next_sync_at, post.last_error = (
            now,
            next_sync_time(post.published_at or now, now, intervals),
            None,
        )
        await session.commit()
        await write_event(
            session,
            event_type=EventType.SYNC_SUCCEEDED,
            account_id=post.account_id,
            post_id=post.id,
        )
        return True
    except Exception as exc:
        post.last_error = str(exc)
        await session.commit()
        await write_event(
            session,
            event_type=EventType.SYNC_FAILED,
            account_id=post.account_id,
            post_id=post.id,
            payload_json={"error": str(exc)},
        )
        return False
