"""Global-option endpoint contracts."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.option import GlobalOptionListResponse, GlobalOptionResponse, GlobalOptionUpdate
from app.services.options import list_all_options, update_existing_option

router = APIRouter(prefix="/options")


@router.get("", response_model=GlobalOptionListResponse)
async def list_options(
    session: AsyncSession = Depends(get_db),
) -> GlobalOptionListResponse:
    """List mutable runtime options."""
    return await list_all_options(session)


@router.patch("/{key}", response_model=GlobalOptionResponse)
async def update_option(
    key: str,
    payload: GlobalOptionUpdate,
    session: AsyncSession = Depends(get_db),
) -> GlobalOptionResponse:
    """Set a mutable runtime option."""
    option = await update_existing_option(session, key, payload)
    if option is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Option not found")
    return option
