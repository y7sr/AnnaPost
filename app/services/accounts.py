"""Accounts service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account import InstagramAccount
from app.repositories.accounts import (
    create_account,
    delete_account,
    get_account_by_default,
    get_account_by_id,
    get_enabled_default_account,
    list_accounts,
    update_account,
)
from app.schemas.account import (
    InstagramAccountCreate,
    InstagramAccountListResponse,
    InstagramAccountResponse,
    InstagramAccountUpdate,
)


async def get_account(
    service_session: AsyncSession, account_id: int
) -> InstagramAccountResponse | None:
    """Get a single account by ID."""
    account = await get_account_by_id(service_session, account_id)
    if account is None:
        return None
    return InstagramAccountResponse.model_validate(account)


async def get_default_account(service_session: AsyncSession) -> InstagramAccount | None:
    """Get the default account."""
    return await get_account_by_default(service_session)


async def get_enabled_default_account_id(service_session: AsyncSession) -> int | None:
    """Get the ID of the enabled default account, or None if none exists."""
    account = await get_enabled_default_account(service_session)
    return account.id if account else None


async def list_all_accounts(service_session: AsyncSession) -> InstagramAccountListResponse:
    """List all accounts."""
    accounts = await list_accounts(service_session)
    return InstagramAccountListResponse(
        accounts=[InstagramAccountResponse.model_validate(a) for a in accounts],
        count=len(accounts),
    )


async def create_new_account(
    service_session: AsyncSession, payload: InstagramAccountCreate
) -> InstagramAccountResponse:
    """Create a new account.

    Enforces the invariant: exactly one account may have is_default=True.
    If the new account is marked as default, any existing default is demoted.
    """
    # If the new account is being set as default, ensure no other default exists
    if payload.is_default:
        existing_default = await get_account_by_default(service_session)
        if existing_default is not None:
            # Demote the existing default
            await update_account(service_session, existing_default.id, is_default=False)

    account = await create_account(
        service_session,
        name=payload.name,
        instagram_user_id=payload.instagram_user_id,
        is_default=payload.is_default,
        enabled=payload.enabled,
        access_token_ref=payload.access_token_ref,
        token_expires_at=payload.token_expires_at,
    )
    return InstagramAccountResponse.model_validate(account)


async def update_existing_account(
    service_session: AsyncSession,
    account_id: int,
    payload: InstagramAccountUpdate,
) -> InstagramAccountResponse | None:
    """Update an existing account.

    Enforces the invariant: exactly one account may have is_default=True.
    If updating an account to be default, any existing default is demoted.
    """
    existing = await get_account_by_id(service_session, account_id)
    if existing is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)

    # If setting this account as default, ensure no other default exists
    if payload.is_default is True:
        existing_default = await get_account_by_default(service_session)
        if existing_default is not None and existing_default.id != account_id:
            # Demote the existing default
            await update_account(service_session, existing_default.id, is_default=False)

    account = await update_account(service_session, account_id, **update_data)
    if account is None:
        return None
    return InstagramAccountResponse.model_validate(account)


async def delete_existing_account(service_session: AsyncSession, account_id: int) -> bool:
    """Delete an account by ID.

    Prevents deletion of the default account if it's the only one.
    """
    account = await get_account_by_id(service_session, account_id)
    if account is None:
        return False

    # Prevent deletion of the only default account
    if account.is_default:
        other_accounts = await list_accounts(service_session)
        if len(other_accounts) <= 1:
            # Cannot delete the only/default account
            return False

    return await delete_account(service_session, account_id)
