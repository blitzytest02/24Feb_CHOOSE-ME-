"""API request and response Pydantic v2 schemas for the Flask REST API layer.

These models define the HTTP request body validation and response serialization
schemas for the document generation API. They map the original JSON event payload
(consumed via the EVENT_DATA environment variable in the Cloud Run Job architecture)
into typed HTTP request body schemas compatible with Flask route handlers.

The request models (GenerateRequest, UpdateRequest) preserve the same JSON payload
schema accepted by the original Cloud Run Job, adapted to HTTP request body format.
Response models (DocumentStatusResponse, JobStatusResponse, ErrorResponse,
JobAcceptedResponse) support the asynchronous background job execution pattern
where document generation is triggered via API and status is polled subsequently.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OperationMode(str, Enum):
    """Dual-mode operation enum reflecting GENERATE and UPDATE capabilities.

    GENERATE: Full Technical Specification generation from repository analysis.
    UPDATE: Incremental update of an existing Technical Specification based on
            repository changes, requiring a previous_tech_spec for comparison.
    """

    GENERATE = "GENERATE"
    UPDATE = "UPDATE"


class JobStatus(str, Enum):
    """Job lifecycle status enum for background document generation tracking.

    PENDING: Job has been accepted but execution has not started.
    IN_PROGRESS: Job is currently executing (document generation underway).
    COMPLETED: Job finished successfully — document is available.
    FAILED: Job encountered an unrecoverable error during execution.
    """

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    """Request body schema for ``POST /api/v1/documents/generate``.

    All fields are derived from the EVENT_DATA JSON payload schema documented
    in the Technical Specification.  Required fields (``project_id``,
    ``tech_spec_id``, ``job_id``, ``repository_url``) are validated to be
    non-empty strings.  The ``mode`` field is locked to ``GENERATE`` via a
    model-level validator.
    """

    project_id: str = Field(
        ...,
        description="Unique project identifier",
    )
    tech_spec_id: str = Field(
        ...,
        description="Technical specification document identifier",
    )
    job_id: str = Field(
        ...,
        description="Unique job execution identifier",
    )
    repository_url: str = Field(
        ...,
        description="URL of the target repository to analyze",
    )
    repository_branch: str = Field(
        default="main",
        description="Branch name to analyze",
    )
    sections: Optional[List[dict]] = Field(
        default=None,
        description="Section definitions from TECHNICAL_SECTION_PROMPTS",
    )
    notification_data: Optional[dict] = Field(
        default=None,
        description="Notification configuration for Pub/Sub events",
    )
    mode: OperationMode = Field(
        default=OperationMode.GENERATE,
        description="Operation mode — must be GENERATE for this endpoint",
    )
    config: Optional[dict] = Field(
        default=None,
        description="Additional configuration overrides",
    )
    attachments: Optional[List[dict]] = Field(
        default=None,
        description="Attachment references from admin service",
    )
    figma_url: Optional[str] = Field(
        default=None,
        description="Optional Figma design file URL for design integration (F-012)",
    )
    previous_tech_spec: Optional[str] = Field(
        default=None,
        description="Previous tech spec for reference — not used in GENERATE mode",
    )

    # -- Field-level validators ------------------------------------------

    @field_validator("project_id", "tech_spec_id", "job_id")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Ensure required identifier fields are not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("Field must not be empty")
        return v.strip()

    # -- Model-level validators ------------------------------------------

    @model_validator(mode="after")
    def validate_generate_mode(self) -> "GenerateRequest":
        """Enforce that the mode field is set to GENERATE for this request type."""
        if self.mode != OperationMode.GENERATE:
            raise ValueError("GenerateRequest mode must be GENERATE")
        return self

    # -- Pydantic v2 configuration ---------------------------------------

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "proj-123",
                "tech_spec_id": "ts-456",
                "job_id": "job-789",
                "repository_url": "https://github.com/org/repo",
                "repository_branch": "main",
                "mode": "GENERATE",
            }
        },
    )


class UpdateRequest(BaseModel):
    """Request body schema for ``POST /api/v1/documents/update``.

    Shares the same base fields as ``GenerateRequest`` but enforces UPDATE
    mode and requires a non-empty ``previous_tech_spec`` for change
    identification against the current repository state.
    """

    project_id: str = Field(
        ...,
        description="Unique project identifier",
    )
    tech_spec_id: str = Field(
        ...,
        description="Technical specification document identifier",
    )
    job_id: str = Field(
        ...,
        description="Unique job execution identifier",
    )
    repository_url: str = Field(
        ...,
        description="URL of the target repository to analyze",
    )
    repository_branch: str = Field(
        default="main",
        description="Branch name to analyze",
    )
    sections: Optional[List[dict]] = Field(
        default=None,
        description="Section definitions",
    )
    notification_data: Optional[dict] = Field(
        default=None,
        description="Notification configuration",
    )
    mode: OperationMode = Field(
        default=OperationMode.UPDATE,
        description="Operation mode — must be UPDATE for this endpoint",
    )
    config: Optional[dict] = Field(
        default=None,
        description="Additional configuration overrides",
    )
    attachments: Optional[List[dict]] = Field(
        default=None,
        description="Attachment references",
    )
    figma_url: Optional[str] = Field(
        default=None,
        description="Optional Figma design file URL",
    )
    previous_tech_spec: str = Field(
        ...,
        description=(
            "Previous Technical Specification content for change identification"
        ),
    )

    # -- Field-level validators ------------------------------------------

    @field_validator("project_id", "tech_spec_id", "job_id")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Ensure required identifier fields are not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("Field must not be empty")
        return v.strip()

    # -- Model-level validators ------------------------------------------

    @model_validator(mode="after")
    def validate_update_mode(self) -> "UpdateRequest":
        """Enforce UPDATE mode and a non-empty previous_tech_spec."""
        if self.mode != OperationMode.UPDATE:
            raise ValueError("UpdateRequest mode must be UPDATE")
        if not self.previous_tech_spec or not self.previous_tech_spec.strip():
            raise ValueError("previous_tech_spec is required for UPDATE mode")
        return self

    # -- Pydantic v2 configuration ---------------------------------------

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "project_id": "proj-123",
                "tech_spec_id": "ts-456",
                "job_id": "job-789",
                "repository_url": "https://github.com/org/repo",
                "repository_branch": "main",
                "mode": "UPDATE",
                "previous_tech_spec": "# Previous Tech Spec\n...",
            }
        },
    )


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class DocumentStatusResponse(BaseModel):
    """Response schema for ``GET /api/v1/documents/<id>/status``.

    Provides real-time progress information for an ongoing or completed
    document generation job, including per-section progress tracking that
    maps to the progressive section upload and Pub/Sub notification model.
    """

    tech_spec_id: str = Field(
        description="Technical specification document identifier",
    )
    job_id: str = Field(
        description="Unique job execution identifier",
    )
    status: JobStatus = Field(
        description="Current job lifecycle status",
    )
    mode: OperationMode = Field(
        description="Operation mode used for this document generation",
    )
    current_section: Optional[int] = Field(
        default=None,
        description="Index of the section currently being processed",
    )
    total_sections: Optional[int] = Field(
        default=None,
        description="Total number of sections in the document",
    )
    completed_sections: Optional[int] = Field(
        default=None,
        description="Number of sections completed so far",
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the job started execution",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the job completed (if finished)",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error details if the job status is FAILED",
    )


class JobStatusResponse(BaseModel):
    """General-purpose job status response for status polling queries.

    Provides a lightweight view of job state with optional timing information
    and a result payload populated upon successful completion.
    """

    job_id: str = Field(
        description="Unique job execution identifier",
    )
    status: JobStatus = Field(
        description="Current job lifecycle status",
    )
    message: str = Field(
        default="",
        description="Human-readable status message",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the job was created",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of the most recent status update",
    )
    result: Optional[dict] = Field(
        default=None,
        description="Final result payload (populated when status is COMPLETED)",
    )


class ErrorResponse(BaseModel):
    """Standardised error response returned by all API error handlers.

    Credentials and sensitive information are never included in error
    messages to comply with the credential security rules.
    """

    error: str = Field(
        description="Short error classification label",
    )
    message: str = Field(
        description="Human-readable error description",
    )
    status_code: int = Field(
        description="HTTP status code associated with the error",
    )


class JobAcceptedResponse(BaseModel):
    """Immediate response returned when a generate or update request is accepted.

    The API returns this response synchronously while the actual document
    generation executes asynchronously in a background thread.  Callers
    use the ``job_id`` to poll for status via the status endpoints.
    """

    job_id: str = Field(
        description="Unique job execution identifier for status polling",
    )
    status: JobStatus = Field(
        default=JobStatus.PENDING,
        description="Initial job status — always PENDING at acceptance time",
    )
    message: str = Field(
        default="Document generation job accepted",
        description="Human-readable acceptance confirmation message",
    )
