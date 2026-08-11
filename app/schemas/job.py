"""Pydantic schemas and payload contracts for Instagram jobs.

The foreign-key columns identify the object being acted on.  Payloads only
carry operation-specific input, which keeps the queue rows small and avoids
duplicating authoritative post/comment data.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models.job import JobStatus, JobType


class JobPayload(BaseModel):
    """Base for strict, JSON-serializable job payloads."""

    model_config = ConfigDict(extra="forbid")


class PublishJobPayload(JobPayload):
    """Payload for ``publish``; the post row contains all required inputs."""


class DeletePostJobPayload(JobPayload):
    """Payload for ``delete_post``; the post row contains the remote ID."""


class CreateCommentJobPayload(JobPayload):
    """Text to publish as a top-level comment on the referenced post."""

    text: str = Field(..., min_length=1, max_length=2200)


class ReplyCommentJobPayload(JobPayload):
    """Text to publish as a reply to the referenced comment."""

    text: str = Field(..., min_length=1, max_length=2200)


type JobPayloadModel = (
    PublishJobPayload | DeletePostJobPayload | CreateCommentJobPayload | ReplyCommentJobPayload
)

PAYLOAD_MODELS: dict[JobType, type[JobPayload]] = {
    JobType.PUBLISH: PublishJobPayload,
    JobType.DELETE_POST: DeletePostJobPayload,
    JobType.CREATE_COMMENT: CreateCommentJobPayload,
    JobType.REPLY_COMMENT: ReplyCommentJobPayload,
}


def validate_job_payload(
    job_type: JobType | str,
    payload: dict[str, Any] | None,
) -> JobPayloadModel:
    """Validate and normalize a payload against its job type.

    ``None`` is treated as ``{}`` for jobs whose inputs come entirely from
    their referenced row.  Payload-bearing jobs still fail validation when
    their required text is absent.
    """
    resolved_type = JobType(job_type)
    model = PAYLOAD_MODELS[resolved_type]
    return model.model_validate(payload or {})


class InstagramJobBase(BaseModel):
    """Base schema for InstagramJob with common fields."""

    model_config = ConfigDict(extra="forbid")

    job_type: JobType = Field(..., description="Type of job to execute")
    account_id: int | None = Field(None, description="ID of the associated account")
    post_id: int | None = Field(None, description="ID of the associated post")
    comment_id: int | None = Field(None, description="ID of the associated comment")
    payload_json: dict[str, Any] | None = Field(
        None, description="Job-specific payload; validated against job_type"
    )
    status: JobStatus = Field(JobStatus.PENDING, description="Current status of the job")
    attempts: int = Field(0, ge=0, description="Number of attempts made")
    max_attempts: int = Field(3, ge=1, description="Maximum number of attempts")
    run_after: datetime | None = Field(None, description="When the job should next be attempted")

    @model_validator(mode="after")
    def validate_payload_for_type(self) -> "InstagramJobBase":
        """Reject a payload whose shape does not match ``job_type``."""
        self.payload_json = validate_job_payload(self.job_type, self.payload_json).model_dump(
            mode="json"
        )
        return self


class InstagramJobCreate(InstagramJobBase):
    """Schema for creating a new job."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_type": "publish",
                "post_id": 1,
                "payload_json": {},
            }
        }
    )


class InstagramJobUpdate(BaseModel):
    """Schema for updating a job."""

    model_config = ConfigDict(extra="forbid")

    status: JobStatus | None = Field(None)
    attempts: int | None = Field(None)
    max_attempts: int | None = Field(None)
    run_after: datetime | None = Field(None)
    last_error: str | None = Field(None)


class InstagramJobResponse(InstagramJobBase):
    """Schema for InstagramJob responses with all fields."""

    id: int = Field(..., description="Job ID")
    locked_at: datetime | None = Field(None, description="When the job was locked for processing")
    locked_by: str | None = Field(None, description="Who locked the job")
    created_at: datetime = Field(..., description="When the job was created")
    started_at: datetime | None = Field(None, description="When the job started")
    completed_at: datetime | None = Field(None, description="When the job completed")
    last_error: str | None = Field(None, description="Last error message")

    model_config = ConfigDict(from_attributes=True)


class InstagramJobListResponse(BaseModel):
    """Schema for listing jobs."""

    jobs: list[InstagramJobResponse] = Field(..., description="List of jobs")
    count: int = Field(..., description="Total number of jobs")
