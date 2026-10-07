import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import Certificate, CertificateStatus, GenerationJob, JobStatus, utcnow
from app.services.certificate_generator import CertificateGenerator
from app.utils.file_utils import get_certificate_filepath

logger = logging.getLogger(__name__)


def process_generation_job(job_id: int, db_session: Optional[Session] = None) -> None:
    """
    Background worker that iterates through all pending certificates for a job,
    generates their PDFs, and updates real-time status in the database.

    Fault tolerance:
    If any single certificate fails generation, it is marked as FAILED with its error
    message recorded. Subsequent certificates continue processing without interruption.

    Args:
        job_id: The ID of the GenerationJob to process.
        db_session: Optional existing database session (primarily for unit tests).
    """
    # Use provided session or create a new dedicated session for background work
    close_session = False
    if db_session is None:
        db = SessionLocal()
        close_session = True
    else:
        db = db_session

    try:
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if not job:
            logger.error(f"[Job {job_id}] Cannot process: Job not found in database.")
            return

        # Mark job as PROCESSING
        job.status = JobStatus.PROCESSING
        job.started_at = utcnow()
        db.commit()
        db.refresh(job)
        logger.info(f"[Job {job_id}] Processing started for {job.total_count} recipients.")

        # Fetch certificates for this job
        certificates = (
            db.query(Certificate)
            .filter(Certificate.job_id == job_id)
            .order_by(Certificate.id.asc())
            .all()
        )

        successful = 0
        failed = 0

        for cert in certificates:
            logger.info(
                f"[Job {job_id}] Generating certificate {cert.id} for recipient '{cert.recipient_name}'."
            )
            try:
                # Target output filepath
                target_filepath = get_certificate_filepath(
                    job_id=job.id,
                    cert_id=cert.id,
                    recipient_name=cert.recipient_name,
                )

                # Generate PDF certificate via service
                CertificateGenerator.generate(
                    recipient_name=cert.recipient_name,
                    title=cert.certificate_title,
                    course=cert.course,
                    organization=cert.organization,
                    event_date=cert.event_date,
                    certificate_id=cert.id,
                    output_path=target_filepath,
                )

                # Update certificate state
                cert.status = CertificateStatus.GENERATED
                cert.file_path = str(target_filepath)
                cert.error_message = None
                successful += 1
                logger.info(
                    f"[Job {job_id}] Certificate {cert.id} generated successfully at {target_filepath.name}."
                )

            except Exception as exc:
                # Failure isolation: record failure without breaking remaining recipients
                cert.status = CertificateStatus.FAILED
                cert.error_message = str(exc)
                failed += 1
                logger.error(
                    f"[Job {job_id}] Failed to generate certificate {cert.id} for '{cert.recipient_name}': {exc}",
                    exc_info=True,
                )

            # Update running counts and persist after each certificate
            # This enables real-time progress monitoring via GET /jobs/{id}
            job.successful_count = successful
            job.failed_count = failed
            db.commit()

        # Update final job state
        job.completed_at = utcnow()
        if failed == 0 and successful > 0:
            job.status = JobStatus.COMPLETED
        elif successful > 0 and failed > 0:
            job.status = JobStatus.COMPLETED_WITH_ERRORS
        else:
            job.status = JobStatus.FAILED

        db.commit()
        logger.info(
            f"[Job {job_id}] Processing complete. Status: {job.status.value}. "
            f"Successful: {successful}, Failed: {failed}, Total: {job.total_count}."
        )

    except Exception as exc:
        logger.critical(f"[Job {job_id}] Unexpected error in job processing: {exc}", exc_info=True)
        try:
            job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
            if job:
                job.status = JobStatus.FAILED
                job.completed_at = utcnow()
                db.commit()
        except Exception:
            db.rollback()
    finally:
        if close_session:
            db.close()
