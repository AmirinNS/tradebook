"""Refresh price bars for universe stocks or seed synthetic demo data."""

import argparse
from datetime import date

from modules.market_source import fetch_daily
from modules.prices import ensure_indexes, upsert_bars
from modules.screener import build_snapshot
from modules.synthetic import generate_ohlcv
from sources.config import db
from sources.universe import DEMO_SYMBOLS, get_live_universe

DEMO_SEEDS = {
    "DEMO1": 101,
    "DEMO2": 102,
    "DEMO3": 103,
    "DEMO4": 104,
    "DEMO5": 105,
}

DEMO_INITIAL_PRICES = {
    "DEMO1": "15.5000",
    "DEMO2": "42.0000",
    "DEMO3": "8.2500",
    "DEMO4": "120.0000",
    "DEMO5": "3.8000",
}

DEMO_START_DATE = date(2025, 8, 18)


def seed_demo_prices(database, sessions=320):
    """Seed deterministic synthetic bars for all demo symbols."""
    total_bars = 0
    for symbol in DEMO_SYMBOLS:
        seed = DEMO_SEEDS.get(symbol, 42)
        initial_price = DEMO_INITIAL_PRICES.get(symbol)
        bars = generate_ohlcv(
            symbol=symbol,
            start=DEMO_START_DATE,
            sessions=sessions,
            seed=seed,
            initial_price=initial_price,
        )
        upserted = upsert_bars(database, symbol, bars)
        print(f"{symbol}: seeded {upserted} bars")
        total_bars += upserted

    print(f"Total demo bars seeded: {total_bars}")
    snapshots = build_snapshot(database)
    print(f"Screener snapshot built: {snapshots} symbols")
    return total_bars


def refresh_live_prices(database):
    """Fetch 2 years of daily bars for all live universe stocks."""
    live_stocks = get_live_universe()
    success_count = 0
    failure_count = 0

    for item in live_stocks:
        symbol = item["symbol"]
        bars = fetch_daily(symbol)
        if bars:
            upserted = upsert_bars(database, symbol, bars)
            print(f"{symbol}: {upserted} bars upserted")
            success_count += 1
        else:
            print(f"{symbol}: no data returned; keeping last-good bars")
            failure_count += 1

    print(f"Refresh completed: {success_count} updated, {failure_count} failed")
    snapshots = build_snapshot(database)
    print(f"Screener snapshot built: {snapshots} symbols")
    return success_count, failure_count


def main():
    parser = argparse.ArgumentParser(
        description="Refresh market prices or seed synthetic demo prices."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Seed 320 sessions per demo symbol (offline demo data).",
    )
    args = parser.parse_args()

    ensure_indexes(db)

    if args.demo:
        seed_demo_prices(db)
    else:
        refresh_live_prices(db)


if __name__ == "__main__":
    main()
