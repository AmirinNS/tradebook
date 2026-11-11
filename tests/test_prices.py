"""Tests for modules.prices, modules.synthetic, and price bar persistence."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128
from pymongo.errors import DuplicateKeyError

from modules.prices import ensure_indexes, get_bars, latest_bar, upsert_bars
from modules.synthetic import generate_ohlcv
from sources.money import to_d128
from sources.universe import (
    DEMO_SYMBOLS,
    get_demo_universe,
    get_live_universe,
    get_universe,
    is_demo_symbol,
)


def test_deterministic_synthetic_data():
    """Verify that synthetic generation is deterministic and obeys OHLC and weekday rules."""
    bars1 = generate_ohlcv("DEMO1", "2024-01-01", 30, seed=42)
    bars2 = generate_ohlcv("DEMO1", "2024-01-01", 30, seed=42)
    bars_diff_seed = generate_ohlcv("DEMO1", "2024-01-01", 30, seed=99)

    assert len(bars1) == 30
    assert bars1 == bars2
    assert bars1 != bars_diff_seed

    for bar in bars1:
        assert bar["symbol"] == "DEMO1"
        assert bar["date"].weekday() < 5, f"Date {bar['date']} must be a weekday"
        assert bar["date"].tzinfo == timezone.utc
        assert isinstance(bar["open"], Decimal)
        assert isinstance(bar["high"], Decimal)
        assert isinstance(bar["low"], Decimal)
        assert isinstance(bar["close"], Decimal)
        assert isinstance(bar["volume"], int)

        assert bar["high"] >= max(bar["open"], bar["close"])
        assert bar["low"] <= min(bar["open"], bar["close"])
        assert bar["low"] > Decimal("0")


def test_synthetic_sessions_validation():
    """Verify generate_ohlcv rejects invalid session counts or initial prices."""
    with pytest.raises(ValueError):
        generate_ohlcv("DEMO1", "2024-01-01", 0)

    with pytest.raises(ValueError):
        generate_ohlcv("DEMO1", "2024-01-01", -5)

    with pytest.raises(ValueError):
        generate_ohlcv("DEMO1", "2024-01-01", 5, initial_price=Decimal("-10.0"))


def test_ensure_indexes_enforces_unique(db):
    """Verify that the compound index on (symbol, date) rejects duplicates."""
    ensure_indexes(db)

    bar_date = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
    doc = {
        "symbol": "DEMO1",
        "date": bar_date,
        "open": to_d128("10.0000"),
        "high": to_d128("11.0000"),
        "low": to_d128("9.5000"),
        "close": to_d128("10.5000"),
        "volume": 50000,
    }

    db.price_bars.insert_one(doc)

    with pytest.raises(DuplicateKeyError):
        db.price_bars.insert_one(
            {
                "symbol": "DEMO1",
                "date": bar_date,
                "open": to_d128("10.0000"),
                "high": to_d128("11.0000"),
                "low": to_d128("9.5000"),
                "close": to_d128("10.5000"),
                "volume": 60000,
            }
        )


def test_idempotent_upsert(db):
    """Verify that repeated upserts do not create duplicate documents."""
    bars = generate_ohlcv("DEMO1", "2024-01-01", 10, seed=123)

    first_run = upsert_bars(db, "DEMO1", bars)
    assert first_run == 10
    assert db.price_bars.count_documents({}) == 10

    # Upsert again with the exact same bars
    second_run = upsert_bars(db, "DEMO1", bars)
    assert second_run == 10
    assert db.price_bars.count_documents({}) == 10


def test_mongo_decimal128_storage(db):
    """Verify raw documents store Decimal128 and get_bars returns Decimal."""
    bars = generate_ohlcv("DEMO1", "2024-01-01", 1, seed=55)
    upsert_bars(db, bars)

    raw_doc = db.price_bars.find_one({"symbol": "DEMO1"})
    assert isinstance(raw_doc["open"], Decimal128)
    assert isinstance(raw_doc["high"], Decimal128)
    assert isinstance(raw_doc["low"], Decimal128)
    assert isinstance(raw_doc["close"], Decimal128)

    stored_bars = get_bars(db, "DEMO1")
    assert len(stored_bars) == 1
    assert isinstance(stored_bars[0]["open"], Decimal)
    assert isinstance(stored_bars[0]["high"], Decimal)
    assert isinstance(stored_bars[0]["low"], Decimal)
    assert isinstance(stored_bars[0]["close"], Decimal)
    assert stored_bars[0]["open"] == bars[0]["open"]


def test_get_bars_filtering_and_order(db):
    """Verify get_bars sorts by date ascending and respects start/end filters."""
    bars = generate_ohlcv("DEMO1", "2024-01-01", 10, seed=77)
    upsert_bars(db, bars)

    all_bars = get_bars(db, "DEMO1")
    assert len(all_bars) == 10
    for i in range(len(all_bars) - 1):
        assert all_bars[i]["date"] < all_bars[i + 1]["date"]

    # Filter with start and end
    mid_start = all_bars[2]["date"]
    mid_end = all_bars[5]["date"]

    filtered = get_bars(db, "DEMO1", start=mid_start, end=mid_end)
    assert len(filtered) == 4
    assert filtered[0]["date"] == mid_start
    assert filtered[-1]["date"] == mid_end


def test_latest_bar(db):
    """Verify latest_bar returns the most recent bar or None."""
    assert latest_bar(db, "UNKNOWN") is None

    bars = generate_ohlcv("DEMO2", "2024-01-01", 5, seed=88)
    upsert_bars(db, bars)

    latest = latest_bar(db, "DEMO2")
    assert latest is not None
    assert latest["date"] == bars[-1]["date"]
    assert latest["close"] == bars[-1]["close"]
    assert isinstance(latest["close"], Decimal)


def test_universe_helpers():
    """Verify stock universe definition and helper functions."""
    all_symbols = get_universe()
    assert len(all_symbols) == 35

    demo_symbols = get_demo_universe()
    assert len(demo_symbols) == 5
    assert [d["symbol"] for d in demo_symbols] == DEMO_SYMBOLS

    live_symbols = get_live_universe()
    assert len(live_symbols) == 30

    assert is_demo_symbol("DEMO1") is True
    assert is_demo_symbol("demo3") is True
    assert is_demo_symbol("AAPL") is False
    assert is_demo_symbol(None) is False
