"""Stock screener snapshot repository and filtering engine."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import pymongo
from pymongo import UpdateOne

import modules.indicators as indicators
import modules.prices as prices
import sources.money as money
import sources.universe as universe

SORT_FIELDS = {
    "symbol": "symbol",
    "name": "name",
    "sector": "sector",
    "exchange": "exchange",
    "currency": "currency",
    "last_close": "last_close",
    "change": "change",
    "change_pct": "change_pct",
    "rsi": "rsi",
    "sma50": "sma50",
    "sma200": "sma200",
    "avg_volume_20": "avg_volume_20",
    "as_of_date": "as_of_date",
}


def ensure_indexes(db):
    """Ensure indexes on screener_snapshot collection.

    Per plan: indexes on sector and rsi to start, plus unique index on symbol.
    """
    db.screener_snapshot.create_index("symbol", unique=True)
    db.screener_snapshot.create_index("sector")
    db.screener_snapshot.create_index("rsi")


def build_snapshot(db):
    """Build one document per universe symbol with price data in screener_snapshot.

    Symbols without price bars are excluded. Numbers are persisted through
    sources/money.py as Decimal128 (including RSI and change %) so MongoDB
    queries compare numerically.

    Returns:
        int: Number of symbol snapshot documents stored.
    """
    universe_stocks = universe.get_universe()
    valid_symbols = []
    operations = []

    for stock in universe_stocks:
        sym = stock["symbol"].strip().upper()
        bars = prices.get_bars(db, sym)
        if not bars:
            continue

        valid_symbols.append(sym)
        latest_bar = bars[-1]
        last_close = latest_bar["close"]
        as_of_date = latest_bar["date"]

        if len(bars) >= 2:
            prev_close = bars[-2]["close"]
            change = last_close - prev_close
            change_pct = (change / prev_close) * Decimal(100) if prev_close else Decimal(0)
        else:
            change = Decimal(0)
            change_pct = Decimal(0)

        closes = [b["close"] for b in bars]
        volumes = [b["volume"] for b in bars]

        sma50_series = indicators.sma(closes, 50)
        sma50 = sma50_series[-1] if len(closes) >= 50 else None

        sma200_series = indicators.sma(closes, 200)
        sma200 = sma200_series[-1] if len(closes) >= 200 else None

        rsi_series = indicators.rsi(closes, 14)
        rsi14 = rsi_series[-1] if len(closes) > 14 else None

        _, _, hist = indicators.macd(closes)
        macd_cross_up = bool(
            len(hist) >= 2
            and hist[-1] is not None
            and hist[-2] is not None
            and hist[-1] > Decimal(0)
            and hist[-2] <= Decimal(0)
        )

        above_sma200 = bool(sma200 is not None and last_close > sma200)

        recent_volumes = volumes[-20:]
        avg_volume_20 = (
            int(round(sum(recent_volumes) / len(recent_volumes)))
            if recent_volumes
            else 0
        )

        q_pct = change_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rsi_d128 = (
            money.to_d128(rsi14.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if rsi14 is not None
            else None
        )

        doc = {
            "symbol": sym,
            "name": stock.get("name", sym),
            "sector": stock.get("sector", ""),
            "exchange": stock.get("exchange", ""),
            "currency": stock.get("currency", "MYR"),
            "as_of_date": as_of_date,
            "last_close": money.to_d128(money.price(last_close)),
            "change": money.to_d128(money.price(change)),
            "change_pct": money.to_d128(q_pct),
            "sma50": money.to_d128(money.price(sma50)) if sma50 is not None else None,
            "sma200": money.to_d128(money.price(sma200)) if sma200 is not None else None,
            "rsi": rsi_d128,
            "macd_cross_up": macd_cross_up,
            "above_sma200": above_sma200,
            "avg_volume_20": avg_volume_20,
        }

        operations.append(
            UpdateOne(
                {"symbol": sym},
                {"$set": doc},
                upsert=True,
            )
        )

    if operations:
        db.screener_snapshot.bulk_write(operations, ordered=False)
        db.screener_snapshot.delete_many({"symbol": {"$nin": valid_symbols}})
    else:
        db.screener_snapshot.delete_many({})

    return len(valid_symbols)


def get_latest_as_of_date(db):
    """Return the most recent as_of_date from screener_snapshot, or None."""
    doc = db.screener_snapshot.find_one(
        {"as_of_date": {"$ne": None}},
        sort=[("as_of_date", pymongo.DESCENDING)],
    )
    if doc and doc.get("as_of_date"):
        return doc["as_of_date"]
    return None


def _format_screener_doc(doc):
    """Convert a MongoDB screener document to python-side Decimal and typed dict."""
    last_close = money.from_d128(doc["last_close"]) if doc.get("last_close") is not None else None
    change = money.from_d128(doc["change"]) if doc.get("change") is not None else Decimal(0)
    change_pct = (
        money.from_d128(doc["change_pct"])
        if doc.get("change_pct") is not None
        else Decimal(0)
    )
    sma50 = money.from_d128(doc["sma50"]) if doc.get("sma50") is not None else None
    sma200 = money.from_d128(doc["sma200"]) if doc.get("sma200") is not None else None
    rsi = money.from_d128(doc["rsi"]) if doc.get("rsi") is not None else None

    as_of = doc.get("as_of_date")
    as_of_str = as_of.strftime("%Y-%m-%d") if as_of else None

    return {
        "symbol": doc["symbol"],
        "name": doc.get("name", doc["symbol"]),
        "sector": doc.get("sector", ""),
        "exchange": doc.get("exchange", ""),
        "currency": doc.get("currency", "MYR"),
        "as_of_date": as_of_str,
        "last_close": last_close,
        "change": change,
        "change_pct": change_pct,
        "sma50": sma50,
        "sma200": sma200,
        "rsi": rsi,
        "macd_cross_up": bool(doc.get("macd_cross_up", False)),
        "above_sma200": bool(doc.get("above_sma200", False)),
        "avg_volume_20": int(doc.get("avg_volume_20", 0)),
        "is_pos": change > Decimal(0),
        "is_neg": change < Decimal(0),
    }


def run_screen(db, filters=None, sort=None, direction=None):
    """Run a stock screen against screener_snapshot as a single MongoDB query.

    Filters supported:
      - rsi_lt: Decimal or numeric string
      - rsi_gt: Decimal or numeric string
      - above_sma200: bool or truthy string
      - macd_cross_up: bool or truthy string
      - sector: str

    Sort is whitelisted to prevent arbitrary field queries.

    Returns:
        List of formatted screener item dictionaries.
    """
    filters = filters or {}
    query = {"last_close": {"$ne": None}}

    # Sector filter
    sector_val = filters.get("sector")
    if sector_val and str(sector_val).strip() and str(sector_val).strip().lower() != "all":
        query["sector"] = str(sector_val).strip()

    # RSI filters
    rsi_query = {}
    if "rsi_lt" in filters and filters["rsi_lt"] is not None and filters["rsi_lt"] != "":
        try:
            lt_val = money.as_decimal(filters["rsi_lt"])
            rsi_query["$lt"] = money.to_d128(lt_val)
            rsi_query["$ne"] = None
        except (ValueError, TypeError, InvalidOperation):
            pass

    if "rsi_gt" in filters and filters["rsi_gt"] is not None and filters["rsi_gt"] != "":
        try:
            gt_val = money.as_decimal(filters["rsi_gt"])
            rsi_query["$gt"] = money.to_d128(gt_val)
        except (ValueError, TypeError, InvalidOperation):
            pass

    if rsi_query:
        query["rsi"] = rsi_query

    # Above SMA200 filter
    above_sma200_val = filters.get("above_sma200")
    if above_sma200_val:
        if isinstance(above_sma200_val, str):
            if above_sma200_val.strip().lower() in ("1", "true", "on", "yes"):
                query["above_sma200"] = True
        elif bool(above_sma200_val):
            query["above_sma200"] = True

    # MACD cross up filter
    macd_val = filters.get("macd_cross_up")
    if macd_val:
        if isinstance(macd_val, str):
            if macd_val.strip().lower() in ("1", "true", "on", "yes"):
                query["macd_cross_up"] = True
        elif bool(macd_val):
            query["macd_cross_up"] = True

    # Sort processing with strict whitelist
    sort_key = "symbol"
    dir_val = pymongo.ASCENDING

    if sort:
        sort_str = str(sort).strip()
        if sort_str.startswith("-"):
            field_candidate = sort_str[1:]
            dir_candidate = pymongo.DESCENDING
        elif sort_str.endswith("_desc"):
            field_candidate = sort_str[:-5]
            dir_candidate = pymongo.DESCENDING
        elif sort_str.endswith("_asc"):
            field_candidate = sort_str[:-4]
            dir_candidate = pymongo.ASCENDING
        else:
            field_candidate = sort_str
            dir_candidate = pymongo.ASCENDING

        if field_candidate in SORT_FIELDS:
            sort_key = SORT_FIELDS[field_candidate]
            dir_val = dir_candidate
            if direction:
                d_str = str(direction).strip().lower()
                if d_str in ("desc", "-1"):
                    dir_val = pymongo.DESCENDING
                elif d_str in ("asc", "1"):
                    dir_val = pymongo.ASCENDING

    sort_spec = [(sort_key, dir_val)]
    if sort_key != "symbol":
        sort_spec.append(("symbol", pymongo.ASCENDING))

    cursor = db.screener_snapshot.find(query).sort(sort_spec)
    return [_format_screener_doc(doc) for doc in cursor]
