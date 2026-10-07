from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.db.models import CertificateStatus, JobStatus


class RecipientCreate(BaseModel):
    """Schema for individual recipient input."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Full name of recipient",
        examples=["Rahul Kumar"],
    )
    email: EmailStr = Field(
        ...,
        description="Valid email address of recipient",
        examples=["rahul@example.com"],
    )

    @field_validator("name")
    @classmethod
    def validate_name_not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Recipient name must not be blank or only whitespace")
        return trimmed


class CertificateGenerateRequest(BaseModel):
    """Schema for batch certificate generation request."""

    title: str = Field(
        default="Certificate of Completion",
        min_length=2,
        max_length=200,
        description="Certificate title or headline",
        examples=["Certificate of Completion"],
    )
    course: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Course, event, or program title",
        examples=["Python Backend Development"],
    )
    organization: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Issuing organization name",
        examples=["Aereo"],
    )
    event_date: str = Field(
        ...,
        description="Event or issue date in YYYY-MM-DD format",
        examples=["2026-10-07"],
    )
    recipients: List[RecipientCreate] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of recipient details for certificate generation",
    )

    @field_validator("title", "course", "organization")
    @classmethod
    def strip_and_validate_non_empty(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Field cannot be empty or solely whitespace")
        return trimmed

    @field_validator("event_date")
    @classmethod
    def validate_date_format(cls, value: str) -> str:
        trimmed = value.strip()
        try:
            date.fromisoformat(trimmed)
        except ValueError:
            raise ValueError("Event date must be a valid date in YYYY-MM-DD format")
        return trimmed


class JobCreateResponse(BaseModel):
    """Response returned upon successfully accepting a certificate generation job."""

    job_id: int
    status: JobStatus
    total_count: int
    message: str

    model_config = ConfigDict(from_attributes=True)


class CertificateItemResponse(BaseModel):
    """Details of an individual recipient's certificate within a job."""

    certificate_id: int
    recipient_name: str
    recipient_email: str
    status: CertificateStatus
    download_url: Optional[str] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class JobStatusResponse(BaseModel):
    """Detailed status and progress report for a generation job."""

    job_id: int
    status: JobStatus
    total: int
    successful: int
    failed: int
    pending: int
    progress_percentage: float
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    certificates: List[CertificateItemResponse]

    model_config = ConfigDict(from_attributes=True)
