"""Pydantic schemas for Instagram comments."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InstagramCommentBase(BaseModel):
    """Base schema for InstagramComment with common fields."""

    account_id: int = Field(..., description="ID of the associated account")
    post_id: int = Field(..., description="ID of the associated post")
    instagram_comment_id: str = Field(
        ..., max_length=255, description="Instagram comment ID (unique)"
    )
    parent_instagram_comment_id: str | None = Field(
        None, max_length=255, description="Parent comment ID for replies"
    )
    username: str | None = Field(None, max_length=255, description="Comment author username")
    instagram_user_id_if_available: str | None = Field(
        None, max_length=255, description="Comment author Instagram user ID"
    )
    text: str | None = Field(None, description="Comment text")
    like_count_if_available: int | None = Field(None, description="Number of likes on the comment")
    is_reply: bool = Field(False, description="Whether this is a reply")
    is_hidden: bool = Field(False, description="Whether the comment is hidden")
    is_deleted_remote: bool = Field(False, description="Whether the comment is deleted remotely")
    raw_json: dict | None = Field(None, description="Raw Instagram API response payload")


class InstagramCommentCreate(InstagramCommentBase):
    """Schema for creating a new local comment (outgoing)."""

    pass


class InstagramCommentResponse(InstagramCommentBase):
    """Schema for InstagramComment responses with all fields."""

    id: int = Field(..., description="Comment ID")
    created_at_remote: datetime | None = Field(
        None, description="When the comment was created on Instagram"
    )
    fetched_at: datetime = Field(..., description="When the comment was fetched")
    updated_at: datetime = Field(..., description="When the comment was last updated")

    model_config = ConfigDict(from_attributes=True)


class InstagramCommentListResponse(BaseModel):
    """Schema for listing comments for a post."""

    comments: list[InstagramCommentResponse] = Field(..., description="List of comments")
    count: int = Field(..., description="Total number of comments")


class CommentCreateRequest(BaseModel):
    """Schema for creating an outgoing comment via API."""

    text: str = Field(..., min_length=1, description="Comment text")
    parent_instagram_comment_id: str | None = Field(
        None, description="Parent comment ID for replies"
    )


class ReplyCreateRequest(BaseModel):
    """Schema for creating a reply to a comment."""

    text: str = Field(..., min_length=1, description="Reply text")
