"""Accounts repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account import InstagramAccount


async def get_account_by_id(session: AsyncSession, account_id: int) -> InstagramAccount | None:
    """Get an account by ID."""
    result = await session.execute(
        select(InstagramAccount).where(InstagramAccount.id == account_id)
    )
    return result.scalar_one_or_none()


async def get_account_by_default(session: AsyncSession) -> InstagramAccount | None:
    """Get the default account (where is_default=True)."""
    result = await session.execute(
        select(InstagramAccount).where(InstagramAccount.is_default.is_(True))
    )
    return result.scalar_one_or_none()


async def get_enabled_default_account(session: AsyncSession) -> InstagramAccount | None:
    """Get the enabled default account."""
    result = await session.execute(
        select(InstagramAccount).where(
            InstagramAccount.is_default.is_(True),
            InstagramAccount.enabled.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def list_accounts(session: AsyncSession) -> list[InstagramAccount]:
    """List all accounts."""
    result = await session.execute(select(InstagramAccount))
    return result.scalars().all()


async def create_account(session: AsyncSession, **kwargs) -> InstagramAccount:
    """Create a new account."""
    account = InstagramAccount(**kwargs)
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def update_account(
    session: AsyncSession, account_id: int, **kwargs
) -> InstagramAccount | None:
    """Update an account by ID."""
    account = await get_account_by_id(session, account_id)
    if account is None:
        return None

    for key, value in kwargs.items():
        if hasattr(account, key):
            setattr(account, key, value)

    await session.commit()
    await session.refresh(account)
    return account


async def delete_account(session: AsyncSession, account_id: int) -> bool:
    """Delete an account by ID."""
    account = await get_account_by_id(session, account_id)
    if account is None:
        return False

    await session.delete(account)
    await session.commit()
    return True
