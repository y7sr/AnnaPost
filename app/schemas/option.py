"""Pydantic schemas for global options."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GlobalOptionBase(BaseModel):
    """Base schema for GlobalOption with common fields."""

    key: str = Field(..., min_length=1, max_length=255, description="Unique option key")
    value_json: dict | list | str | int | float | bool | None = Field(
        None, description="JSON-serializable value"
    )


class GlobalOptionCreate(GlobalOptionBase):
    """Schema for creating a new global option."""

    pass


class GlobalOptionUpdate(BaseModel):
    """Schema for updating a global option."""

    value_json: dict | list | str | int | float | bool | None = Field(None, description="New value")


class GlobalOptionResponse(GlobalOptionBase):
    """Schema for GlobalOption responses with all fields."""

    updated_at: datetime = Field(..., description="When the option was last updated")

    model_config = ConfigDict(from_attributes=True)


class GlobalOptionListResponse(BaseModel):
    """Schema for listing global options."""

    options: list[GlobalOptionResponse] = Field(..., description="List of global options")
    count: int = Field(..., description="Total number of options")
