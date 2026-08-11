"""Options service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.options import (
    create_option,
    delete_option,
    get_option_by_key,
    list_options,
    update_option,
)
from app.schemas.option import (
    GlobalOptionListResponse,
    GlobalOptionResponse,
    GlobalOptionUpdate,
)


async def get_option(service_session: AsyncSession, key: str) -> GlobalOptionResponse | None:
    """Get a single option by key."""
    option = await get_option_by_key(service_session, key)
    if option is None:
        return None
    return GlobalOptionResponse.model_validate(option)


async def list_all_options(service_session: AsyncSession) -> GlobalOptionListResponse:
    """List all options."""
    options = await list_options(service_session)
    return GlobalOptionListResponse(
        options=[GlobalOptionResponse.model_validate(o) for o in options],
        count=len(options),
    )


async def create_new_option(
    service_session: AsyncSession,
    key: str,
    value_json: dict | list | str | int | float | bool | None,
) -> GlobalOptionResponse:
    """Create a new option."""
    option = await create_option(service_session, key, value_json)
    return GlobalOptionResponse.model_validate(option)


async def update_existing_option(
    service_session: AsyncSession, key: str, payload: GlobalOptionUpdate
) -> GlobalOptionResponse | None:
    """Update an existing option by key."""
    option = await update_option(service_session, key, payload.value_json)
    if option is None:
        option = await create_option(service_session, key, payload.value_json)
    return GlobalOptionResponse.model_validate(option)


async def delete_existing_option(service_session: AsyncSession, key: str) -> bool:
    """Delete an option by key."""
    return await delete_option(service_session, key)


async def get_option_value(
    service_session: AsyncSession,
    key: str,
    default: dict | list | str | int | float | bool | None = None,
) -> dict | list | str | int | float | bool | None:
    """Get the raw value of an option, with a default if not found.

    This is a convenience method for services that need the actual value
    rather than the full option object.
    """
    option = await get_option_by_key(service_session, key)
    if option is None:
        return default
    return option.value_json
