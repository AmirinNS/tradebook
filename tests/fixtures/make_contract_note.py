"""Generate the project's fictional contract-note layout in memory for tests."""

from io import BytesIO

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

TITLE = "Tradebook synthetic contract note v1"
DISCLAIMER = "Demo layout. All values are fictional. Not a real broker format."


def make_contract_note(*, side="buy", pages=1, password=None, image_only=False, **overrides):
    """Return PDF bytes; overrides also allow intentionally invalid test fields."""
    fields = {
        "Contract number": "SYN-2026-0001",
        "Trade date": "2026-11-02",
        "Settlement date": "2026-11-04",
        "Stock code": "DEMO1",
        "Stock name": "Fictional Demo Shares",
        "Side": side,
        "Quantity": "100",
        "Price (RM)": "10.0000",
        "Brokerage (RM)": "8.00",
        "Clearing fee (RM)": "0.30",
        "Stamp duty (RM)": "1.00",
        "Tax (RM)": "0.64",
        "Net amount (RM)": "1009.94" if side == "buy" else "990.06",
    }
    fields.update(overrides)
    output = BytesIO()
    encryption = StandardEncryption(password) if password is not None else None
    canvas = Canvas(output, pagesize=A4, encrypt=encryption, invariant=True)
    canvas.setTitle("Synthetic contract note")
    if image_only:
        canvas.drawImage(ImageReader(Image.new("RGB", (200, 200), "white")), 48, 500)
    else:
        canvas.setFont("Helvetica-Bold", 16)
        canvas.drawString(48, 790, TITLE)
        canvas.setFont("Helvetica", 10)
        canvas.drawString(48, 766, DISCLAIMER)
        for index, (label, value) in enumerate(fields.items()):
            canvas.drawString(48, 730 - index * 24, f"{label}: {value}")
    canvas.showPage()
    for _ in range(pages - 1):
        canvas.showPage()
    canvas.save()
    return output.getvalue()
