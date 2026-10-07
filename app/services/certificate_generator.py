from pathlib import Path
from typing import Union

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas


class CertificateGenerator:
    """
    Service responsible for generating professional PDF certificates
    using a predefined, elegant template layout.
    """

    # Palette
    COLOR_PRIMARY = colors.HexColor("#0F294A")    # Deep Navy
    COLOR_ACCENT = colors.HexColor("#C59B27")     # Warm Classic Gold
    COLOR_TEXT_MUTED = colors.HexColor("#5A6B82") # Slate Gray
    COLOR_BORDER_LIGHT = colors.HexColor("#E2E8F0") # Subtle divider

    @classmethod
    def generate(
        cls,
        recipient_name: str,
        title: str,
        course: str,
        organization: str,
        event_date: str,
        certificate_id: int,
        output_path: Union[str, Path],
    ) -> Path:
        """
        Generate a single landscape PDF certificate and write to output_path.

        Args:
            recipient_name: Name of the recipient.
            title: Headline title (e.g., 'Certificate of Completion').
            course: Course, workshop, or event name.
            organization: Name of the issuing organization.
            event_date: Date string (e.g., '2026-10-07').
            certificate_id: Unique database ID of the certificate.
            output_path: Target filesystem path to save the PDF.

        Returns:
            Path: The resolved path to the created PDF file.
        """
        path = Path(output_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        # Standard Letter Landscape: 792 x 612 pt
        page_width, page_height = landscape(letter)
        c = canvas.Canvas(str(path), pagesize=(page_width, page_height))
        c.setTitle(f"{title} - {recipient_name}")
        c.setAuthor(organization)
        c.setSubject(course)

        # 1. Background borders
        cls._draw_decorative_borders(c, page_width, page_height)

        # 2. Organization Header
        c.setFont("Helvetica-Bold", 15)
        c.setFillColor(cls.COLOR_TEXT_MUTED)
        c.drawCentredString(page_width / 2.0, page_height - 90, organization.upper())

        # 3. Certificate Title
        c.setFont("Helvetica-Bold", 28)
        c.setFillColor(cls.COLOR_PRIMARY)
        c.drawCentredString(page_width / 2.0, page_height - 135, title.upper())

        # Gold decorative accent bar under title
        c.setStrokeColor(cls.COLOR_ACCENT)
        c.setLineWidth(2)
        c.line(page_width / 2.0 - 100, page_height - 150, page_width / 2.0 + 100, page_height - 150)

        # 4. Presentation statement
        c.setFont("Helvetica", 13)
        c.setFillColor(cls.COLOR_TEXT_MUTED)
        c.drawCentredString(page_width / 2.0, page_height - 195, "THIS IS PROUDLY PRESENTED TO")

        # 5. Recipient Name
        c.setFont("Helvetica-Bold", 26)
        c.setFillColor(cls.COLOR_PRIMARY)
        c.drawCentredString(page_width / 2.0, page_height - 245, recipient_name)

        # Recipient name underline accent
        name_width = min(max(c.stringWidth(recipient_name, "Helvetica-Bold", 26) + 40, 180), 450)
        c.setStrokeColor(cls.COLOR_ACCENT)
        c.setLineWidth(1.5)
        c.line(page_width / 2.0 - (name_width / 2.0), page_height - 258, page_width / 2.0 + (name_width / 2.0), page_height - 258)

        # 6. Completion text and Course name
        c.setFont("Helvetica", 12)
        c.setFillColor(cls.COLOR_TEXT_MUTED)
        c.drawCentredString(page_width / 2.0, page_height - 295, "for successfully completing the course in")

        c.setFont("Helvetica-Bold", 18)
        c.setFillColor(cls.COLOR_PRIMARY)
        c.drawCentredString(page_width / 2.0, page_height - 330, course)

        # 7. Decorative Gold Seal in the bottom center
        cls._draw_medallion(c, page_width / 2.0, 140)

        # 8. Footer Left: Issue Date
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(cls.COLOR_PRIMARY)
        c.drawString(80, 150, "DATE OF ISSUE")
        c.setStrokeColor(cls.COLOR_TEXT_MUTED)
        c.setLineWidth(0.75)
        c.line(80, 142, 220, 142)
        c.setFont("Helvetica", 10)
        c.setFillColor(cls.COLOR_TEXT_MUTED)
        c.drawString(80, 125, event_date)

        # 9. Footer Right: Authorized Signatory
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(cls.COLOR_PRIMARY)
        c.drawString(page_width - 220, 150, "AUTHORIZED SIGNATURE")
        c.setStrokeColor(cls.COLOR_TEXT_MUTED)
        c.setLineWidth(0.75)
        c.line(page_width - 220, 142, page_width - 80, 142)
        c.setFont("Helvetica-Oblique", 11)
        c.setFillColor(cls.COLOR_PRIMARY)
        c.drawString(page_width - 210, 125, f"{organization} Authority")

        # 10. Bottom Identifier (Certificate Verification ID)
        c.setFont("Helvetica", 9)
        c.setFillColor(cls.COLOR_TEXT_MUTED)
        cert_id_formatted = f"CERTIFICATE ID: CERT-{certificate_id:06d}"
        c.drawCentredString(page_width / 2.0, 48, cert_id_formatted)

        # Finalize and write PDF
        c.showPage()
        c.save()

        return path

    @classmethod
    def _draw_decorative_borders(cls, c: canvas.Canvas, width: float, height: float) -> None:
        """Draw dual-layer luxury borders with corner accents."""
        # Outer border
        margin_outer = 25
        c.setStrokeColor(cls.COLOR_PRIMARY)
        c.setLineWidth(4)
        c.rect(margin_outer, margin_outer, width - (2 * margin_outer), height - (2 * margin_outer))

        # Inner border
        margin_inner = 33
        c.setStrokeColor(cls.COLOR_ACCENT)
        c.setLineWidth(1.5)
        c.rect(margin_inner, margin_inner, width - (2 * margin_inner), height - (2 * margin_inner))

        # Corner corner square accents
        corner_size = 12
        for x, y in [
            (margin_inner - 2, margin_inner - 2),
            (width - margin_inner - corner_size + 2, margin_inner - 2),
            (margin_inner - 2, height - margin_inner - corner_size + 2),
            (width - margin_inner - corner_size + 2, height - margin_inner - corner_size + 2),
        ]:
            c.setFillColor(cls.COLOR_ACCENT)
            c.setStrokeColor(cls.COLOR_PRIMARY)
            c.setLineWidth(1)
            c.rect(x, y, corner_size, corner_size, fill=1, stroke=1)

    @classmethod
    def _draw_medallion(cls, c: canvas.Canvas, cx: float, cy: float) -> None:
        """Draw an ornamental verification medallion badge."""
        # Outer gold circle
        c.setStrokeColor(cls.COLOR_ACCENT)
        c.setFillColor(colors.HexColor("#FEF3C7")) # Very soft warm gold fill
        c.setLineWidth(2)
        c.circle(cx, cy, 26, fill=1, stroke=1)

        # Inner dotted/dashed circle
        c.setStrokeColor(cls.COLOR_PRIMARY)
        c.setLineWidth(1)
        c.circle(cx, cy, 21, fill=0, stroke=1)

        # Star / Emblem text in center
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(cls.COLOR_PRIMARY)
        c.drawCentredString(cx, cy - 3, "VERIFIED")
