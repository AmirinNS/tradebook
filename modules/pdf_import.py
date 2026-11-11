"""Parse one fictional MYR contract note from the project's synthetic layout."""

import re
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO

import pdfplumber
from pdfminer.pdfdocument import PDFEncryptionError
from pdfminer.pdfexceptions import PDFException
from pdfminer.psexceptions import PSException
from pdfplumber.utils.exceptions import PdfminerException

from sources.money import money, price

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10
MAX_TEXT_BYTES = 200 * 1024
TITLE = "Tradebook synthetic contract note v1"
DISCLAIMER = "Demo layout. All values are fictional. Not a real broker format."
FIELDS = (
    "Contract number", "Trade date", "Settlement date", "Stock code", "Stock name",
    "Side", "Quantity", "Price (RM)", "Brokerage (RM)", "Clearing fee (RM)",
    "Stamp duty (RM)", "Tax (RM)", "Net amount (RM)",
)


def parse_contract_note(pdf_bytes):
    """Return (rows, reconciliation) or raise ValueError for an invalid PDF.

    Only this project's labelled synthetic layout is supported. Reconciliation
    mismatch is a warning requiring explicit acknowledgement, not a parse error.
    """
    if not isinstance(pdf_bytes, bytes):
        raise TypeError("parse_contract_note expects bytes")
    if len(pdf_bytes) > MAX_BYTES:
        raise ValueError("PDF files must be at most 5 MB.")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("Choose a PDF file with a valid %PDF- header.")
    text = _extract_text(pdf_bytes)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines[:2] != [TITLE, DISCLAIMER]:
        raise ValueError("Unsupported PDF layout. Use the synthetic contract note format.")
    fields = {}
    for line in lines[2:]:
        label, separator, value = line.partition(": ")
        if not separator or label not in FIELDS or label in fields or not value.strip():
            raise ValueError("Malformed synthetic contract note fields.")
        fields[label] = value.strip()
    if set(fields) != set(FIELDS):
        raise ValueError("Synthetic contract note is missing required fields.")
    return _parse_fields(fields)


def _extract_text(pdf_bytes):
    try:
        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            if pdf.doc.encryption:
                raise PDFEncryptionError("Encrypted document")
            if len(pdf.pages) > MAX_PAGES:
                raise ValueError("PDF files must have at most 10 pages.")
            parts, size = [], 0
            for page in pdf.pages:
                text = page.extract_text() or ""
                size += len(text.encode("utf-8")) + bool(parts)
                if size > MAX_TEXT_BYTES:
                    raise ValueError("PDF extracted text exceeds the 200 KB limit.")
                parts.append(text)
    except PDFEncryptionError:
        raise ValueError("Encrypted PDFs are not supported. Upload an unencrypted PDF.") from None
    except (PdfminerException, PDFException, PSException) as error:
        if error.args and isinstance(error.args[0], PDFEncryptionError):
            raise ValueError(
                "Encrypted PDFs are not supported. Upload an unencrypted PDF."
            ) from None
        raise ValueError("Malformed PDF. Upload a valid synthetic contract note.") from None
    text = "\n".join(parts)
    if not text.strip():
        raise ValueError("Image-only or empty PDFs are not supported. Select a text PDF.")
    return text


def _parse_fields(fields):
    if not re.fullmatch(r"[A-Z0-9-]{1,64}", fields["Contract number"]):
        raise ValueError("Contract number must use uppercase letters, digits or hyphens.")
    if len(fields["Stock name"]) > 160:
        raise ValueError("Stock name must be at most 160 characters.")
    trading_day, settlement_day = (_parse_date(fields[label]) for label in (
        "Trade date", "Settlement date",
    ))
    if settlement_day < trading_day:
        raise ValueError("Settlement date cannot precede trade date.")
    symbol, side = fields["Stock code"], fields["Side"].lower()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,31}", symbol):
        raise ValueError("Stock code must be an uppercase ticker of at most 32 characters.")
    if side not in ("buy", "sell"):
        raise ValueError("Side must be buy or sell.")
    if not re.fullmatch(r"[0-9]{1,12}", fields["Quantity"]) or int(fields["Quantity"]) <= 0:
        raise ValueError("Quantity must be a positive whole number of shares, at most 12 digits.")
    quantity = int(fields["Quantity"])
    unit_price = _amount(fields["Price (RM)"], 4, "Price")
    if unit_price <= 0:
        raise ValueError("Price must be positive.")
    fees = money(sum((_amount(fields[label], 2, label) for label in (
        "Brokerage (RM)", "Clearing fee (RM)", "Stamp duty (RM)", "Tax (RM)",
    )), Decimal(0)))
    net = _amount(fields["Net amount (RM)"], 2, "Net amount", signed=True)
    gross = money(Decimal(quantity) * unit_price)
    expected = money(gross + fees if side == "buy" else gross - fees)
    row = {
        "symbol": symbol, "side": side, "qty": quantity, "price": price(unit_price),
        "fees": fees, "date": datetime.combine(trading_day, datetime.min.time(), timezone.utc),
        "source": "pdf",
    }
    return [row], {
        "contract_number": fields["Contract number"], "stock_name": fields["Stock name"],
        "settlement_date": settlement_day, "gross": gross, "fees": fees,
        "net": net, "expected_net": expected,
        "requires_acknowledgement": abs(net - expected) > Decimal("0.01"),
    }


def _parse_date(value):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Trade and settlement dates must use YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("Trade and settlement dates must be real calendar dates.") from None


def _amount(value, places, label, *, signed=False):
    sign = "-?" if signed else ""
    if not re.fullmatch(rf"{sign}[0-9]{{1,12}}(?:\.[0-9]{{1,{places}}})?", value):
        constraint = "a number" if signed else "non-negative"
        raise ValueError(f"{label} must be {constraint} with at most {places} decimal places.")
    return Decimal(value)
