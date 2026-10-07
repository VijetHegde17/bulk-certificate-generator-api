import enum
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utcnow() -> datetime:
    """Helper to return current UTC datetime."""
    return datetime.now(timezone.utc)


class JobStatus(str, enum.Enum):
    """Execution status for a batch certificate generation job."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"


class CertificateStatus(str, enum.Enum):
    """Generation status for an individual recipient's certificate."""
    PENDING = "PENDING"
    GENERATED = "GENERATED"
    FAILED = "FAILED"


class GenerationJob(Base):
    """Represents a bulk certificate generation job requested by a client."""

    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    course: Mapped[str] = mapped_column(String(200), nullable=False)
    organization: Mapped[str] = mapped_column(String(200), nullable=False)
    event_date: Mapped[str] = mapped_column(String(50), nullable=False)

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )
    total_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # One-to-many relationship: A job contains multiple recipient certificates
    certificates: Mapped[List["Certificate"]] = relationship(
        "Certificate",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="Certificate.id",
    )


class Certificate(Base):
    """Represents an individual certificate generated for a recipient."""

    __tablename__ = "certificates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("generation_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    certificate_title: Mapped[str] = mapped_column(String(200), nullable=False)
    course: Mapped[str] = mapped_column(String(200), nullable=False)
    organization: Mapped[str] = mapped_column(String(200), nullable=False)
    event_date: Mapped[str] = mapped_column(String(50), nullable=False)

    status: Mapped[CertificateStatus] = mapped_column(
        Enum(CertificateStatus, native_enum=False),
        default=CertificateStatus.PENDING,
        nullable=False,
        index=True,
    )
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Many-to-one relationship back to the parent generation job
    job: Mapped["GenerationJob"] = relationship("GenerationJob", back_populates="certificates")
