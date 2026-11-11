"""Price bar repository: persistence and retrieval of OHLCV bars in MongoDB."""

from datetime import date, datetime, timezone

import pymongo

from sources.money import from_d128, price, to_d128


def _normalize_date(val):
    """Normalize a date, datetime, or ISO string to UTC midnight datetime."""
    if isinstance(val, datetime):
        return datetime(val.year, val.month, val.day, 0, 0, 0, tzinfo=timezone.utc)
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day, 0, 0, 0, tzinfo=timezone.utc)
    if isinstance(val, str):
        parsed = date.fromisoformat(val.strip())
        return datetime(parsed.year, parsed.month, parsed.day, 0, 0, 0, tzinfo=timezone.utc)
    raise TypeError(f"Expected date, datetime or ISO string, got {type(val).__name__}")


def _doc_to_bar(doc):
    """Convert a price_bars MongoDB document to an application bar dict."""
    d = doc["date"]
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)

    return {
        "symbol": doc["symbol"],
        "date": d,
        "open": from_d128(doc["open"]),
        "high": from_d128(doc["high"]),
        "low": from_d128(doc["low"]),
        "close": from_d128(doc["close"]),
        "volume": int(doc["volume"]),
    }


def ensure_indexes(db):
    """Ensure unique index on (symbol, date) in price_bars collection."""
    db.price_bars.create_index(
        [("symbol", pymongo.ASCENDING), ("date", pymongo.ASCENDING)],
        unique=True,
    )


def upsert_bars(db, symbol_or_bars, bars=None):
    """Idempotently upsert OHLCV bars into price_bars.

    Can be called as:
      upsert_bars(db, bars)               # where each bar in bars has 'symbol'
      upsert_bars(db, 'DEMO1', bars)      # symbol explicitly specified

    Prices are stored as Decimal128 via sources.money.to_d128.
    Dates are stored as UTC midnight datetime.

    Returns:
        Number of bars processed.
    """
    if bars is None:
        bar_list = symbol_or_bars
        default_symbol = None
    else:
        bar_list = bars
        default_symbol = str(symbol_or_bars).strip().upper()

    if not bar_list:
        return 0

    operations = []
    for bar in bar_list:
        sym = (default_symbol if default_symbol else bar["symbol"]).strip().upper()
        bar_date = _normalize_date(bar["date"])

        doc = {
            "symbol": sym,
            "date": bar_date,
            "open": to_d128(price(bar["open"])),
            "high": to_d128(price(bar["high"])),
            "low": to_d128(price(bar["low"])),
            "close": to_d128(price(bar["close"])),
            "volume": int(bar["volume"]),
        }

        operations.append(
            pymongo.UpdateOne(
                {"symbol": sym, "date": bar_date},
                {"$set": doc},
                upsert=True,
            )
        )

    if operations:
        db.price_bars.bulk_write(operations, ordered=False)

    return len(operations)


def get_bars(db, symbol, start=None, end=None):
    """Retrieve OHLCV bars for a symbol sorted ascending by date.

    Prices are converted to Decimal using sources.money.from_d128.

    Args:
        db: MongoDB database object.
        symbol: Ticker symbol string.
        start: Optional start date/datetime filter (inclusive).
        end: Optional end date/datetime filter (inclusive).

    Returns:
        List of bar dicts with Decimal prices and UTC datetime.
    """
    clean_symbol = symbol.strip().upper()
    query = {"symbol": clean_symbol}

    date_filter = {}
    if start is not None:
        date_filter["$gte"] = _normalize_date(start)
    if end is not None:
        date_filter["$lte"] = _normalize_date(end)

    if date_filter:
        query["date"] = date_filter

    cursor = db.price_bars.find(query).sort("date", pymongo.ASCENDING)
    return [_doc_to_bar(doc) for doc in cursor]


def latest_bar(db, symbol):
    """Retrieve the most recent bar for a symbol, or None if no bars exist.

    Prices are converted to Decimal using sources.money.from_d128.
    """
    clean_symbol = symbol.strip().upper()
    doc = db.price_bars.find_one(
        {"symbol": clean_symbol},
        sort=[("date", pymongo.DESCENDING)],
    )
    if doc is None:
        return None
    return _doc_to_bar(doc)
