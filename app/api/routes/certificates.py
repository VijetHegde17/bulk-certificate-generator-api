import io
import logging
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Certificate, CertificateStatus, GenerationJob, JobStatus
from app.schemas.certificate import (
    CertificateGenerateRequest,
    CertificateItemResponse,
    JobCreateResponse,
    JobStatusResponse,
)
from app.services.job_processor import process_generation_job
from app.utils.file_utils import sanitize_filename, validate_safe_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/certificates", tags=["Certificates"])


@router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=JobCreateResponse,
    summary="Create a bulk certificate generation job",
    description=(
        "Accepts a certificate generation request with multiple recipients. "
        "Validates input, records pending entries, and triggers background generation."
    ),
)
def create_certificate_job(
    request: CertificateGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    """
    Initiate bulk certificate generation in the background.
    Returns HTTP 202 with job tracking details immediately.
    """
    total_count = len(request.recipients)
    logger.info(
        f"Received generation request for course '{request.course}' with {total_count} recipients."
    )

    # 1. Create the parent job record
    job = GenerationJob(
        title=request.title,
        course=request.course,
        organization=request.organization,
        event_date=request.event_date,
        status=JobStatus.PENDING,
        total_count=total_count,
        successful_count=0,
        failed_count=0,
    )
    db.add(job)
    db.flush()  # Flush to obtain job.id before creating child records

    # 2. Pre-create individual recipient certificate rows
    for recipient in request.recipients:
        cert = Certificate(
            job_id=job.id,
            recipient_name=recipient.name,
            recipient_email=recipient.email,
            certificate_title=request.title,
            course=request.course,
            organization=request.organization,
            event_date=request.event_date,
            status=CertificateStatus.PENDING,
        )
        db.add(cert)

    db.commit()
    db.refresh(job)

    logger.info(f"Created GenerationJob ID {job.id} containing {total_count} certificates.")

    # 3. Schedule asynchronous generation via FastAPI BackgroundTasks
    background_tasks.add_task(process_generation_job, job.id)

    return JobCreateResponse(
        job_id=job.id,
        status=job.status,
        total_count=job.total_count,
        message="Certificate generation job accepted and processing in background",
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status and progress",
    description="Check the execution status, progress percentage, and recipient results of a generation job.",
)
def get_job_status(
    job_id: int,
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Optional pagination limit for certificate items"),
    offset: int = Query(0, ge=0, description="Optional pagination offset for certificate items"),
    db: Session = Depends(get_db),
) -> JobStatusResponse:
    """
    Fetch real-time status and certificate items for a specific job.
    """
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if not job:
        logger.warning(f"Job status requested for non-existent job ID {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate job with ID {job_id} not found",
        )

    # Calculate pending count and progress percentage
    processed = job.successful_count + job.failed_count
    pending = max(0, job.total_count - processed)
    progress_percentage = round((processed / job.total_count) * 100.0, 2) if job.total_count > 0 else 0.0

    # Query certificates with optional pagination
    cert_query = db.query(Certificate).filter(Certificate.job_id == job_id).order_by(Certificate.id.asc())
    if limit is not None:
        cert_query = cert_query.offset(offset).limit(limit)
    certificates = cert_query.all()

    cert_items = [
        CertificateItemResponse(
            certificate_id=cert.id,
            recipient_name=cert.recipient_name,
            recipient_email=cert.recipient_email,
            status=cert.status,
            download_url=f"/api/v1/certificates/{cert.id}" if cert.status == CertificateStatus.GENERATED else None,
            error_message=cert.error_message,
        )
        for cert in certificates
    ]

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        total=job.total_count,
        successful=job.successful_count,
        failed=job.failed_count,
        pending=pending,
        progress_percentage=progress_percentage,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        certificates=cert_items,
    )


@router.get(
    "/{certificate_id}",
    summary="Download a generated certificate PDF",
    description="Retrieve and download the generated PDF for an individual recipient.",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "The generated PDF certificate file.",
        },
        400: {"description": "Certificate is still pending or generation failed."},
        404: {"description": "Certificate or file not found."},
    },
)
def get_certificate_file(
    certificate_id: int,
    db: Session = Depends(get_db),
):
    """
    Retrieve the generated PDF certificate by ID with strict path validation.
    """
    cert = db.query(Certificate).filter(Certificate.id == certificate_id).first()
    if not cert:
        logger.warning(f"Download requested for non-existent certificate ID {certificate_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate with ID {certificate_id} not found",
        )

    if cert.status == CertificateStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Certificate generation is still pending. Please check again shortly.",
        )

    if cert.status == CertificateStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Certificate generation failed: {cert.error_message or 'Unknown error'}",
        )

    if not cert.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate file path is not recorded",
        )

    try:
        # Enforce security validation to prevent path traversal
        safe_file_path = validate_safe_path(cert.file_path)
    except ValueError as exc:
        logger.error(f"Directory traversal check failed for certificate {certificate_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid certificate file location",
        )

    if not safe_file_path.exists() or not safe_file_path.is_file():
        logger.error(f"Certificate file missing on disk: {safe_file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate file does not exist on disk",
        )

    safe_name = sanitize_filename(cert.recipient_name)
    download_filename = f"Certificate_{cert.id}_{safe_name}.pdf"

    return FileResponse(
        path=safe_file_path,
        media_type="application/pdf",
        filename=download_filename,
    )


@router.get(
    "/jobs/{job_id}/zip",
    summary="Download all generated certificates for a job as a ZIP file",
    description="Convenience endpoint to retrieve all successfully generated certificates in a single archive.",
)
def download_job_certificates_zip(
    job_id: int,
    db: Session = Depends(get_db),
):
    """
    Packages all successfully generated certificates for a job into a ZIP archive.
    """
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID {job_id} not found",
        )

    successful_certs = (
        db.query(Certificate)
        .filter(Certificate.job_id == job_id, Certificate.status == CertificateStatus.GENERATED)
        .all()
    )

    if not successful_certs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No generated certificates available to download for this job.",
        )

    # Build ZIP stream in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for cert in successful_certs:
            if cert.file_path:
                try:
                    file_path = validate_safe_path(cert.file_path)
                    if file_path.exists() and file_path.is_file():
                        safe_name = sanitize_filename(cert.recipient_name)
                        arcname = f"Certificate_{cert.id}_{safe_name}.pdf"
                        zf.write(file_path, arcname=arcname)
                except ValueError:
                    continue

    zip_buffer.seek(0)
    zip_filename = f"job_{job_id}_certificates.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )
