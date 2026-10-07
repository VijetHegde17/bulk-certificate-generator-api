from pathlib import Path
from app.services.certificate_generator import CertificateGenerator


def test_certificate_pdf_generation_file_creation(tmp_path: Path):
    """Verify that CertificateGenerator produces a valid, readable PDF file."""
    output_file = tmp_path / "test_certificate.pdf"

    generated_path = CertificateGenerator.generate(
        recipient_name="Aditi Verma",
        title="Certificate of Achievement",
        course="Cloud Architecture & Microservices",
        organization="Aereo Engineering",
        event_date="2026-10-07",
        certificate_id=101,
        output_path=output_file,
    )

    # 1. Assert file exists on disk
    assert generated_path.exists()
    assert generated_path.is_file()

    # 2. Assert reasonable file size
    file_size = generated_path.stat().st_size
    assert file_size > 1500, f"Expected PDF file size > 1.5KB, got {file_size}"

    # 3. Assert valid PDF header
    with open(generated_path, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-", f"Expected PDF magic header, got {header!r}"
