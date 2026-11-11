"""Seed demo user, demo portfolio, and demo trades for offline showcase."""

from decimal import Decimal

import modules.fees as fees
import modules.portfolios as portfolios
import modules.trades as trades
import modules.users as users
from sources.config import DEMO_USER_EMAIL, db
from sources.functions import utcnow
from sources.universe import DEMO_SYMBOLS

DEMO_PORTFOLIO_NAME = "Bursa journal"

# 20 trades on DEMO symbols spread across the last 3 months of synthetic bars (Aug–Nov 2026)
DEMO_TRADES = [
    ("DEMO1", "buy", 1000, "24.2000", "2026-08-11"),
    ("DEMO2", "buy", 500, "39.0000", "2026-08-15"),
    ("DEMO3", "buy", 2000, "9.1000", "2026-08-20"),
    ("DEMO4", "buy", 300, "105.0000", "2026-08-25"),
    ("DEMO5", "buy", 4000, "4.2000", "2026-08-28"),
    ("DEMO1", "sell", 500, "25.1000", "2026-09-02"),
    ("DEMO1", "buy", 800, "23.5000", "2026-09-08"),
    ("DEMO2", "sell", 200, "41.5000", "2026-09-12"),
    ("DEMO3", "sell", 1000, "8.8000", "2026-09-18"),
    ("DEMO2", "buy", 400, "40.5000", "2026-09-22"),
    ("DEMO5", "sell", 2000, "4.0500", "2026-09-25"),
    ("DEMO4", "buy", 200, "110.0000", "2026-10-02"),
    ("DEMO4", "sell", 250, "115.0000", "2026-10-06"),
    ("DEMO3", "buy", 1500, "9.3000", "2026-10-12"),
    ("DEMO1", "sell", 600, "24.0000", "2026-10-16"),
    ("DEMO5", "buy", 3000, "3.9000", "2026-10-20"),
    ("DEMO2", "sell", 300, "42.8000", "2026-10-23"),
    ("DEMO1", "buy", 500, "23.2000", "2026-10-28"),
    ("DEMO3", "sell", 1000, "9.6000", "2026-11-02"),
    ("DEMO4", "sell", 150, "121.0000", "2026-11-04"),
]


def seed_demo(database):
    """Seed the demo user, Bursa journal portfolio, and trades idempotently."""
    # Ensure DEMO price bars exist
    bars_count = database.price_bars.count_documents({"symbol": {"$in": DEMO_SYMBOLS}})
    if bars_count == 0:
        raise RuntimeError(
            "Demo price bars missing. Run `uv run python -m scripts.refresh_prices --demo` first."
        )

    # 1. Create or retrieve demo user with unusable password
    user_doc = users.get_by_email(database, DEMO_USER_EMAIL)
    if not user_doc:
        user_id = database.users.insert_one({
            "email": DEMO_USER_EMAIL,
            "password_hash": "!",
            "created_at": utcnow(),
        }).inserted_id
    else:
        user_id = user_doc["_id"]
        if user_doc.get("password_hash") != "!":
            database.users.update_one({"_id": user_id}, {"$set": {"password_hash": "!"}})

    # 2. Create or retrieve "Bursa journal" portfolio
    portfolio = database.portfolios.find_one({"user_id": user_id, "name": DEMO_PORTFOLIO_NAME})
    if not portfolio:
        portfolio_id = portfolios.create_portfolio(
            database, user_id=user_id, name=DEMO_PORTFOLIO_NAME, currency="MYR"
        )
        portfolio = database.portfolios.find_one({"_id": portfolio_id})
    else:
        portfolio_id = portfolio["_id"]

    # 3. Check existing trades for idempotency
    existing_trades = trades.list_trades(database, portfolio_id)
    if len(existing_trades) >= len(DEMO_TRADES):
        print(f"Demo portfolio already seeded with {len(existing_trades)} trades.")
        return portfolio_id

    # 4. Insert trades sequentially through modules.trades.add_trade
    for symbol, side, qty, price_str, trade_date in DEMO_TRADES:
        price_dec = Decimal(price_str)
        fee_est = fees.estimate_bursa_fees(side, qty, price_dec)
        current_portfolio = database.portfolios.find_one({"_id": portfolio_id})
        trades.add_trade(
            database,
            user_id=user_id,
            portfolio_id=portfolio_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price_val=price_dec,
            fees_val=fee_est["total"],
            trade_date=trade_date,
            expected_version=current_portfolio["version"],
            source="manual",
        )

    print(f"Demo seed complete: {len(DEMO_TRADES)} trades seeded for {DEMO_PORTFOLIO_NAME}.")
    return portfolio_id


def main():
    seed_demo(db)


if __name__ == "__main__":
    main()
