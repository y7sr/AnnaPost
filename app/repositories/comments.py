"""Comment persistence helpers."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.comment import InstagramComment


async def list_comments(session: AsyncSession, post_id: int) -> list[InstagramComment]:
    return (
        (
            await session.execute(
                select(InstagramComment)
                .where(InstagramComment.post_id == post_id)
                .order_by(InstagramComment.created_at_remote)
            )
        )
        .scalars()
        .all()
    )


async def get_comment(session: AsyncSession, comment_id: int) -> InstagramComment | None:
    return await session.get(InstagramComment, comment_id)


async def upsert_comment(
    session: AsyncSession,
    *,
    account_id: int,
    post_id: int,
    instagram_comment_id: str,
    **values: object,
) -> InstagramComment:
    row = (
        await session.execute(
            select(InstagramComment).where(
                InstagramComment.instagram_comment_id == instagram_comment_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = InstagramComment(
            account_id=account_id,
            post_id=post_id,
            instagram_comment_id=instagram_comment_id,
            **values,
        )
        session.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return row
