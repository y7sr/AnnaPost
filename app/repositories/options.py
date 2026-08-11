"""Options repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.global_option import GlobalOption


async def get_option_by_key(session: AsyncSession, key: str) -> GlobalOption | None:
    """Get an option by key."""
    result = await session.execute(select(GlobalOption).where(GlobalOption.key == key))
    return result.scalar_one_or_none()


async def list_options(session: AsyncSession) -> list[GlobalOption]:
    """List all options."""
    result = await session.execute(select(GlobalOption))
    return result.scalars().all()


async def create_option(
    session: AsyncSession, key: str, value_json: dict | list | str | int | float | bool | None
) -> GlobalOption:
    """Create a new option."""
    option = GlobalOption(key=key, value_json=value_json)
    session.add(option)
    await session.commit()
    await session.refresh(option)
    return option


async def update_option(
    session: AsyncSession, key: str, value_json: dict | list | str | int | float | bool | None
) -> GlobalOption | None:
    """Update an option by key."""
    option = await get_option_by_key(session, key)
    if option is None:
        return None

    option.value_json = value_json
    await session.commit()
    await session.refresh(option)
    return option


async def delete_option(session: AsyncSession, key: str) -> bool:
    """Delete an option by key."""
    option = await get_option_by_key(session, key)
    if option is None:
        return False

    await session.delete(option)
    await session.commit()
    return True
