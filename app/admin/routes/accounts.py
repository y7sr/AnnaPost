"""Admin routes for Instagram accounts."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.template_utils import render_template, render_template_with_status
from app.db.session import get_db
from app.schemas.account import (
    InstagramAccountCreate,
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

router = APIRouter()


@router.get("/")
async def list_accounts_page(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Render accounts list page."""
    accounts_list = await list_all_accounts(session)
    return render_template(
        "accounts.html",
        request=request,
        accounts=accounts_list.accounts,
        count=accounts_list.count,
    )


@router.get("/new/")
async def new_account_page(
    request: Request,
):
    """Render new account form."""
    return render_template(
        "account_new.html",
        request=request,
        account=None,
    )


@router.get("/{account_id}/")
async def get_account_page(
    request: Request,
    account_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Render account detail page."""
    account = await get_account_service(session, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    return render_template(
        "account_detail.html",
        request=request,
        account=account,
    )


@router.get("/{account_id}/edit/")
async def edit_account_page(
    request: Request,
    account_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Render account edit form."""
    account = await get_account_service(session, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    return render_template(
        "account_edit.html",
        request=request,
        account=account,
    )


@router.post("/")
async def create_account_page(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """Create a new account via form submission."""
    form_data = await request.form()

    name = form_data.get("name", "").strip()
    instagram_user_id = form_data.get("instagram_user_id", None)
    if instagram_user_id:
        instagram_user_id = instagram_user_id.strip() or None

    is_default = form_data.get("is_default", "false").lower() == "true"
    enabled = form_data.get("enabled", "true").lower() == "true"
    access_token_ref = form_data.get("access_token_ref", "").strip() or None

    if not name:
        return render_template_with_status(
            "account_new.html",
            status_code=400,
            request=request,
            account=None,
            error="Account name is required",
        )

    payload = InstagramAccountCreate(
        name=name,
        instagram_user_id=instagram_user_id,
        is_default=is_default,
        enabled=enabled,
        access_token_ref=access_token_ref,
    )

    await create_new_account(session, payload)
    return RedirectResponse(url="/admin/accounts/", status_code=303)


@router.post("/{account_id}/edit/")
async def update_account_page(
    request: Request,
    account_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Update an account via form submission."""
    account = await get_account_service(session, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    form_data = await request.form()

    name = form_data.get("name", "").strip()
    instagram_user_id = form_data.get("instagram_user_id", None)
    if instagram_user_id:
        instagram_user_id = instagram_user_id.strip() or None

    is_default = form_data.get("is_default", "false").lower() == "true"
    enabled = form_data.get("enabled", "true").lower() == "true"

    if not name:
        return render_template_with_status(
            "account_edit.html",
            status_code=400,
            request=request,
            account=account,
            error="Account name is required",
        )

    update_values = {
        "name": name,
        "instagram_user_id": instagram_user_id,
        "is_default": is_default,
        "enabled": enabled,
    }
    access_token_ref = form_data.get("access_token_ref", "").strip()
    if access_token_ref:
        update_values["access_token_ref"] = access_token_ref

    payload = InstagramAccountUpdate(**update_values)

    updated_account = await update_existing_account(session, account_id, payload)
    if updated_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    return RedirectResponse(url="/admin/accounts/", status_code=303)


@router.post("/{account_id}/delete/")
async def delete_account_page(
    request: Request,
    account_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Delete an account via form submission."""
    account = await get_account_service(session, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    # Prevent deletion of the only default account
    if account.is_default:
        accounts_list = await list_all_accounts(session)
        if accounts_list.count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete the only default account",
            )

    success = await delete_existing_account(session, account_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    return RedirectResponse(url="/admin/accounts/", status_code=303)
