"""Strict parser for the trades CSV: date,symbol,side,qty,price,fees.

Returns (rows, errors). A row keeps the ledger trade shape without portfolio_id
or seq, with source "csv", so the confirm path can build Trade records, assign
seq on insert and replay the full proposed history through pnl.fifo_positions.
Errors are human-readable strings that name the source line number. Nothing is
written here and no database is touched; the caller decides what a non-empty error
list means for the preview.
"""

import csv
import io
import re
from datetime import date, datetime, timezone

from sources.money import money, parse_decimal, price

COLUMNS = ("date", "symbol", "side", "qty", "price", "fees")
HEADER_LINE = ",".join(COLUMNS)
MAX_BYTES = 1024 * 1024
MAX_ROWS = 5000
SYMBOL_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9.-]{0,31}")
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
QTY_PATTERN = re.compile(r"[0-9]+")


def parse_trades_csv(text):
    """Return (rows, errors) for trades CSV text, or ([], [reason]) wholesale.

    A bad header, an empty file, a file over MAX_BYTES or more than MAX_ROWS rows
    rejects the whole file. Anything else collects one error per bad row and still
    returns the rows that parsed, so the caller can preview both lists. Cells are
    stripped, side is matched case-insensitively and normalized to lower case.
    """
    if not isinstance(text, str):
        raise TypeError("parse_trades_csv expects text")
    if len(text.encode("utf-8")) > MAX_BYTES:
        return [], [f"File is larger than the {MAX_BYTES // 1024} KB limit."]
    try:
        records = _read_records(text)
    except csv.Error as exc:
        return [], [f"File could not be read as CSV: {exc}"]
    if not records:
        return [], ["File is empty."]
    header, data = records[0][1], records[1:]
    if [cell.strip().lower() for cell in header] != list(COLUMNS):
        return [], [f"Header must be {HEADER_LINE}."]
    if len(data) > MAX_ROWS:
        return [], [f"File has {len(data)} rows; the limit is {MAX_ROWS}."]
    rows, errors = [], []
    for line, record in data:
        row, error = _parse_row(record)
        if error:
            errors.append(f"Line {line}: {error}")
        else:
            rows.append(row)
    return rows, errors


def _read_records(text):
    """Return (line number, cells) for every non-blank record, header included.

    newline="" leaves line endings to csv, so LF, CRLF and a lone carriage return
    all read the same way. Blank lines are dropped but still consume their line
    number.
    """
    reader = csv.reader(io.StringIO(text.removeprefix("\ufeff"), newline=""))
    records = []
    for cells in reader:
        if not any(cell.strip() for cell in cells):
            continue
        records.append((reader.line_num, cells))
    return records


def _parse_row(cells):
    """Validate one record, returning (row, None) or (None, message)."""
    if len(cells) != len(COLUMNS):
        return None, f"expected {len(COLUMNS)} columns, got {len(cells)}."
    day, symbol, side, qty, price_text, fees_text = (cell.strip() for cell in cells)
    symbol = symbol.upper()  # broker exports often use lowercase tickers
    side = side.lower()
    if not DATE_PATTERN.fullmatch(day):
        return None, "date must be an ISO date, YYYY-MM-DD."
    try:
        trading_day = date.fromisoformat(day)
    except ValueError:
        return None, "date is not a real calendar date."
    if not SYMBOL_PATTERN.fullmatch(symbol):
        return None, "symbol must be a ticker (letters, digits, dot or dash)."
    if side.lower() not in ("buy", "sell"):
        return None, "side must be buy or sell."
    if not QTY_PATTERN.fullmatch(qty) or int(qty) <= 0:
        return None, "qty must be a positive whole number of shares."
    try:
        price_value, fees_value = parse_decimal(price_text), parse_decimal(fees_text)
    except ValueError:
        return None, "price and fees must be numbers."
    if price_value <= 0 or price_value != price(price_value):
        return None, "price must be positive with at most 4 decimal places."
    if fees_value < 0 or fees_value != money(fees_value):
        return None, "fees cannot be negative and allow at most 2 decimal places."
    return (
        {
            "symbol": symbol,
            "side": side.lower(),
            "qty": int(qty),
            "price": price(price_value),
            "fees": money(fees_value),
            "date": datetime(
                trading_day.year, trading_day.month, trading_day.day, tzinfo=timezone.utc
            ),
            "source": "csv",
        },
        None,
    )
