"""Pydantic schemas for Instagram events."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.event import EventType


class InstagramEventBase(BaseModel):
    """Base schema for InstagramEvent with common fields."""

    event_type: EventType = Field(..., description="Type of event")
    account_id: int | None = Field(None, description="ID of the associated account")
    post_id: int | None = Field(None, description="ID of the associated post")
    job_id: int | None = Field(None, description="ID of the associated job")
    payload_json: dict | None = Field(None, description="Event-specific payload")


class InstagramEventCreate(InstagramEventBase):
    """Schema for creating a new event."""

    pass


class InstagramEventResponse(InstagramEventBase):
    """Schema for InstagramEvent responses with all fields."""

    id: int = Field(..., description="Event ID")
    created_at: datetime = Field(..., description="When the event was created")

    model_config = ConfigDict(from_attributes=True)


class InstagramEventListResponse(BaseModel):
    """Schema for listing events."""

    events: list[InstagramEventResponse] = Field(..., description="List of events")
    count: int = Field(..., description="Total number of events")
