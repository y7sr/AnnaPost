"""Account endpoint contracts."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.account import (
    InstagramAccountCreate,
    InstagramAccountListResponse,
    InstagramAccountResponse,
    InstagramAccountUpdate,
)
from app.services.accounts import (
    create_new_account,
    delete_existing_account,
    list_all_accounts,
    update_existing_account,
)
from app.services.accounts import (
    get_account as get_account_service,
)

router = APIRouter(prefix="/accounts")


@router.get("", response_model=InstagramAccountListResponse)
async def list_accounts(
    session: AsyncSession = Depends(get_db),
) -> InstagramAccountListResponse:
    """List configured Instagram accounts."""
    return await list_all_accounts(session)


@router.post("", response_model=InstagramAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: InstagramAccountCreate,
    session: AsyncSession = Depends(get_db),
) -> InstagramAccountResponse:
    """Create an account configuration."""
    return await create_new_account(session, payload)


@router.get("/{account_id}", response_model=InstagramAccountResponse)
async def get_account(
    account_id: int,
    session: AsyncSession = Depends(get_db),
) -> InstagramAccountResponse:
    """Get one account."""
    account = await get_account_service(session, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.patch("/{account_id}", response_model=InstagramAccountResponse)
async def update_account(
    account_id: int,
    payload: InstagramAccountUpdate,
    session: AsyncSession = Depends(get_db),
) -> InstagramAccountResponse:
    """Update a configured account."""
    account = await update_existing_account(session, account_id, payload)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: int, session: AsyncSession = Depends(get_db)) -> None:
    """Remove a non-sole-default account."""
    if not await delete_existing_account(session, account_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found or sole default"
        )
