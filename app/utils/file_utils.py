import re
from pathlib import Path
from typing import Union

from app.core.config import settings


def sanitize_filename(name: str) -> str:
    """
    Sanitize recipient or course names for safe filesystem usage.
    Removes dangerous characters, spaces, and path traversal sequences.
    """
    # Replace spaces with underscores
    cleaned = re.sub(r"\s+", "_", name.strip())
    # Remove anything that isn't alphanumeric, underscore, or hyphen
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "", cleaned)
    # Truncate to reasonable length
    return cleaned[:40] or "recipient"


def generate_certificate_filename(job_id: int, cert_id: int, recipient_name: str) -> str:
    """
    Generate a sanitized, standardized filename for a certificate.
    Example: cert_j1_c42_Rahul_Kumar.pdf
    """
    safe_name = sanitize_filename(recipient_name)
    return f"cert_j{job_id}_c{cert_id}_{safe_name}.pdf"


def get_certificate_filepath(job_id: int, cert_id: int, recipient_name: str) -> Path:
    """
    Generate a deterministic, secure file path within the configured certificates directory.
    Example: generated_certificates/cert_j1_c42_Rahul_Kumar.pdf
    """
    filename = generate_certificate_filename(job_id, cert_id, recipient_name)
    target_path = settings.certificates_dir_path / filename
    return target_path


def validate_safe_path(target_path: Union[str, Path]) -> Path:
    """
    Verify that the target file path resides strictly inside the configured
    generated certificates directory to prevent directory traversal attacks.
    Raises ValueError if path escapes the intended directory.
    """
    base_dir = settings.certificates_dir_path.resolve()
    resolved_path = Path(target_path).resolve()

    try:
        # Raises ValueError if resolved_path is not within base_dir
        resolved_path.relative_to(base_dir)
    except ValueError:
        raise ValueError("Security violation: Attempted path traversal outside allowed directory")

    return resolved_path
