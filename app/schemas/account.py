"""Pydantic schemas for Instagram accounts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InstagramAccountBase(BaseModel):
    """Base schema for InstagramAccount with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Internal account name")
    instagram_user_id: str | None = Field(None, max_length=255, description="Instagram user ID")
    is_default: bool = Field(False, description="Whether this is the default account")
    enabled: bool = Field(True, description="Whether the account is enabled")
    token_expires_at: datetime | None = Field(None, description="When the access token expires")


class InstagramAccountCreate(InstagramAccountBase):
    """Schema for creating a new InstagramAccount."""

    access_token_ref: str | None = Field(
        None, max_length=500, description="Reference to access token (write-only)"
    )

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "name": "Primary Account",
                "instagram_user_id": "123456789",
                "is_default": True,
                "enabled": True,
                "access_token_ref": "env:ACCOUNT_1_ACCESS_TOKEN",
            }
        },
    )


class InstagramAccountUpdate(BaseModel):
    """Schema for updating an InstagramAccount."""

    name: str | None = Field(None, min_length=1, max_length=255)
    instagram_user_id: str | None = Field(None, max_length=255)
    is_default: bool | None = Field(None)
    enabled: bool | None = Field(None)
    access_token_ref: str | None = Field(None, max_length=500)
    token_expires_at: datetime | None = Field(None)

    model_config = ConfigDict(extra="forbid")


class InstagramAccountResponse(InstagramAccountBase):
    """Schema for InstagramAccount responses with all fields."""

    id: int = Field(..., description="Account ID")
    created_at: datetime = Field(..., description="When the account was created")
    updated_at: datetime = Field(..., description="When the account was last updated")
    last_successful_api_call_at: datetime | None = Field(
        None, description="Last successful API call timestamp"
    )
    last_error_at: datetime | None = Field(None, description="Last error timestamp")
    last_error: str | None = Field(None, description="Last error message")

    model_config = ConfigDict(from_attributes=True)


class InstagramAccountListResponse(BaseModel):
    """Schema for listing InstagramAccounts."""

    accounts: list[InstagramAccountResponse] = Field(..., description="List of Instagram accounts")
    count: int = Field(..., description="Total number of accounts")
