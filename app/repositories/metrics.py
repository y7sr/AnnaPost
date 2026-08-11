"""Append-only metric snapshot helpers."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.metrics import InstagramPostMetric


async def create_snapshot(
    session: AsyncSession, *, post_id: int, **values: object
) -> InstagramPostMetric:
    row = InstagramPostMetric(post_id=post_id, **values)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_snapshots(session: AsyncSession, post_id: int) -> list[InstagramPostMetric]:
    return (
        (
            await session.execute(
                select(InstagramPostMetric)
                .where(InstagramPostMetric.post_id == post_id)
                .order_by(InstagramPostMetric.captured_at.desc())
            )
        )
        .scalars()
        .all()
    )
