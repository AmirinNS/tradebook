"""Tests for Milestone C2: portfolios, trades, FIFO replay, concurrency, and fees."""

from datetime import datetime, timezone
from decimal import Decimal

from bson.objectid import ObjectId

import modules.prices as prices


def test_portfolio_create_and_list(logged_in_client, db):
    """Test creating portfolios and listing them."""
    # Empty listing
    res = logged_in_client.get("/portfolios")
    assert res.status_code == 200
    assert b"No portfolios yet" in res.data

    # Create portfolio
    res = logged_in_client.post(
        "/portfolios/new",
        data={"name": "Bursa Main", "currency": "MYR"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Bursa Main" in res.data
    assert b"MYR portfolio" in res.data

    # Verify document in DB
    p_doc = db.portfolios.find_one({"name": "Bursa Main"})
    assert p_doc is not None
    assert p_doc["currency"] == "MYR"
    assert p_doc["version"] == 1

    # Listing now contains the portfolio
    res = logged_in_client.get("/portfolios")
    assert res.status_code == 200
    assert b"Bursa Main" in res.data


def test_cross_user_isolation(logged_in_client, db):
    """Ensure cross-user read and write actions strictly return 404."""
    # User 1 creates portfolio and a trade
    res = logged_in_client.post(
        "/portfolios/new",
        data={"name": "User1 Portfolio", "currency": "MYR"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    p1 = db.portfolios.find_one({"name": "User1 Portfolio"})
    p1_id = str(p1["_id"])

    logged_in_client.post(
        f"/portfolios/{p1_id}/trades/new",
        data={
            "symbol": "DEMO1",
            "side": "buy",
            "qty": "100",
            "price": "10.0000",
            "fees": "8.00",
            "date": "2026-11-01",
            "version": p1["version"],
        },
        follow_redirects=False,
    )
    t1 = db.trades.find_one({"portfolio_id": p1["_id"]})
    assert t1 is not None
    t1_id = str(t1["_id"])

    # Log out User 1, then register and log in User 2
    logged_in_client.post("/logout")
    logged_in_client.post(
        "/register",
        data={"email": "other@example.com", "password": "password123"},
    )
    logged_in_client.post(
        "/login",
        data={"email": "other@example.com", "password": "password123"},
    )

    # Cross-user read returns 404
    assert logged_in_client.get(f"/portfolios/{p1_id}").status_code == 404

    # Cross-user trade form GET returns 404
    assert logged_in_client.get(f"/portfolios/{p1_id}/trades/new").status_code == 404
    assert logged_in_client.get(f"/portfolios/{p1_id}/trades/{t1_id}/edit").status_code == 404

    # Cross-user write returns 404
    post_add = logged_in_client.post(
        f"/portfolios/{p1_id}/trades/new",
        data={
            "symbol": "DEMO1",
            "side": "buy",
            "qty": "50",
            "price": "10.0000",
            "fees": "5.00",
            "date": "2026-11-02",
            "version": 2,
        },
    )
    assert post_add.status_code == 404

    post_edit = logged_in_client.post(
        f"/portfolios/{p1_id}/trades/{t1_id}/edit",
        data={
            "symbol": "DEMO1",
            "side": "buy",
            "qty": "80",
            "price": "10.0000",
            "fees": "5.00",
            "date": "2026-11-01",
            "version": 2,
        },
    )
    assert post_edit.status_code == 404

    post_del = logged_in_client.post(
        f"/portfolios/{p1_id}/trades/{t1_id}/delete",
        data={"version": 2},
    )
    assert post_del.status_code == 404

    # Assert User 1's trade is untouched
    assert db.trades.count_documents({"portfolio_id": p1["_id"]}) == 1


def test_currency_mismatch_rejected(logged_in_client, db):
    """Ensure trades in a currency differing from the portfolio are rejected."""
    logged_in_client.post(
        "/portfolios/new",
        data={"name": "MYR Book", "currency": "MYR"},
    )
    p = db.portfolios.find_one({"name": "MYR Book"})
    p_id = str(p["_id"])

    # AAPL is USD in the universe, portfolio is MYR
    res = logged_in_client.post(
        f"/portfolios/{p_id}/trades/new",
        data={
            "symbol": "AAPL",
            "side": "buy",
            "qty": "10",
            "price": "150.0000",
            "fees": "1.00",
            "date": "2026-11-01",
            "version": p["version"],
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Trade currency must match the portfolio currency" in res.data
    assert db.trades.count_documents({"portfolio_id": p["_id"]}) == 0

    # Create USD portfolio and try to add DEMO1 (MYR)
    logged_in_client.post(
        "/portfolios/new",
        data={"name": "USD Book", "currency": "USD"},
    )
    p_usd = db.portfolios.find_one({"name": "USD Book"})
    p_usd_id = str(p_usd["_id"])

    res = logged_in_client.post(
        f"/portfolios/{p_usd_id}/trades/new",
        data={
            "symbol": "DEMO1",
            "side": "buy",
            "qty": "100",
            "price": "10.0000",
            "fees": "8.00",
            "date": "2026-11-01",
            "version": p_usd["version"],
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Trade currency must match the portfolio currency" in res.data
    assert db.trades.count_documents({"portfolio_id": p_usd["_id"]}) == 0


def test_stale_version_409(logged_in_client, db):
    """Ensure a stale version token returns HTTP 409 conflict and saves nothing."""
    logged_in_client.post(
        "/portfolios/new",
        data={"name": "Versioned Book", "currency": "MYR"},
    )
    p = db.portfolios.find_one({"name": "Versioned Book"})
    p_id = str(p["_id"])
    assert p["version"] == 1

    # Post with stale version 0
    res = logged_in_client.post(
        f"/portfolios/{p_id}/trades/new",
        data={
            "symbol": "DEMO1",
            "side": "buy",
            "qty": "100",
            "price": "10.0000",
            "fees": "8.00",
            "date": "2026-11-01",
            "version": 0,
        },
    )
    assert res.status_code == 409
    assert db.trades.count_documents({"portfolio_id": p["_id"]}) == 0

    # Add a valid trade with version 1
    res = logged_in_client.post(
        f"/portfolios/{p_id}/trades/new",
        data={
            "symbol": "DEMO1",
            "side": "buy",
            "qty": "100",
            "price": "10.0000",
            "fees": "8.00",
            "date": "2026-11-01",
            "version": 1,
        },
        follow_redirects=False,
    )
    assert res.status_code == 302
    p_updated = db.portfolios.find_one({"_id": p["_id"]})
    assert p_updated["version"] == 2

    # Attempting another write with version 1 now returns 409
    res = logged_in_client.post(
        f"/portfolios/{p_id}/trades/new",
        data={
            "symbol": "DEMO1",
            "side": "buy",
            "qty": "50",
            "price": "11.0000",
            "fees": "5.00",
            "date": "2026-11-02",
            "version": 1,
        },
    )
    assert res.status_code == 409
    assert db.trades.count_documents({"portfolio_id": p["_id"]}) == 1


def test_invalid_historical_edit_rejected(logged_in_client, db):
    """Ensure editing or deleting an earlier buy that invalidates a later sell is rejected."""
    logged_in_client.post(
        "/portfolios/new",
        data={"name": "Replay Book", "currency": "MYR"},
    )
    p = db.portfolios.find_one({"name": "Replay Book"})
    p_id = str(p["_id"])

    # Day 1: Buy 100 DEMO1
    logged_in_client.post(
        f"/portfolios/{p_id}/trades/new",
        data={
            "symbol": "DEMO1",
            "side": "buy",
            "qty": "100",
            "price": "10.0000",
            "fees": "8.00",
            "date": "2026-11-01",
            "version": 1,
        },
    )
    # Day 2: Sell 100 DEMO1
    logged_in_client.post(
        f"/portfolios/{p_id}/trades/new",
        data={
            "symbol": "DEMO1",
            "side": "sell",
            "qty": "100",
            "price": "12.0000",
            "fees": "8.00",
            "date": "2026-11-02",
            "version": 2,
        },
    )
    assert db.trades.count_documents({"portfolio_id": p["_id"]}) == 2

    buy_trade = db.trades.find_one({"portfolio_id": p["_id"], "side": "buy"})
    buy_id = str(buy_trade["_id"])

    # Attempt to edit Day 1 buy from 100 shares to 50 shares
    p_current = db.portfolios.find_one({"_id": p["_id"]})
    res = logged_in_client.post(
        f"/portfolios/{p_id}/trades/{buy_id}/edit",
        data={
            "symbol": "DEMO1",
            "side": "buy",
            "qty": "50",
            "price": "10.0000",
            "fees": "8.00",
            "date": "2026-11-01",
            "version": p_current["version"],
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Sell exceeds open quantity for DEMO1" in res.data

    # Verify Day 1 buy is still 100 shares in DB!
    buy_check = db.trades.find_one({"_id": ObjectId(buy_id)})
    assert buy_check["qty"] == 100

    # Attempt to delete Day 1 buy
    p_current = db.portfolios.find_one({"_id": p["_id"]})
    res = logged_in_client.post(
        f"/portfolios/{p_id}/trades/{buy_id}/delete",
        data={"version": p_current["version"]},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Sell exceeds open quantity for DEMO1" in res.data

    # Verify Day 1 buy is still in DB!
    assert db.trades.count_documents({"portfolio_id": p["_id"]}) == 2


def test_open_positions_and_realized_dashboard(logged_in_client, db):
    """Verify open positions, unrealized P/L with price bars, and realized lot portions."""
    # Seed a price bar for DEMO1
    bar_date = datetime(2026, 11, 10, 0, 0, 0, tzinfo=timezone.utc)
    prices.upsert_bars(
        db,
        "DEMO1",
        [
            {
                "symbol": "DEMO1",
                "date": bar_date,
                "open": Decimal("13.0000"),
                "high": Decimal("13.6000"),
                "low": Decimal("12.8000"),
                "close": Decimal("13.4000"),
                "volume": 10000,
            }
        ],
    )

    logged_in_client.post(
        "/portfolios/new",
        data={"name": "Trading Dashboard", "currency": "MYR"},
    )
    p = db.portfolios.find_one({"name": "Trading Dashboard"})
    p_id = str(p["_id"])

    # Buy 200 shares @ 12.0000, fees 10.00
    logged_in_client.post(
        f"/portfolios/{p_id}/trades/new",
        data={
            "symbol": "DEMO1",
            "side": "buy",
            "qty": "200",
            "price": "12.0000",
            "fees": "10.00",
            "date": "2026-11-01",
            "version": 1,
        },
    )

    # Sell 100 shares @ 14.0000, fees 8.00
    logged_in_client.post(
        f"/portfolios/{p_id}/trades/new",
        data={
            "symbol": "DEMO1",
            "side": "sell",
            "qty": "100",
            "price": "14.0000",
            "fees": "8.00",
            "date": "2026-11-05",
            "version": 2,
        },
    )

    res = logged_in_client.get(f"/portfolios/{p_id}")
    assert res.status_code == 200
    page = res.data.decode("utf-8")

    # Realized portion calculation:
    # Entry: 100 @ 12.00, Buy fee share: 5.00
    # Exit: 100 @ 14.00, Sell fee: 8.00
    # Net P/L = 100 * (14 - 12) - 5 - 8 = 200 - 13 = +187.00
    assert "+187.00" in page
    assert "100.0%" in page  # Win rate shows 1 decimal place per DESIGN.md
    assert "1 of 1 closed lot portions" in page

    # Open position calculation:
    # 100 remaining shares.
    # Total cost = 100 * 12.00 + 5.00 remaining fee = 1205.00.
    # Cost per share = 12.0500.
    # Last close = 13.4000.
    # Market value = 1340.00.
    # Unrealized = 1340.00 - 1205.00 = +135.00.
    assert "12.0500" in page  # Cost/share
    assert "13.4000" in page  # Last close
    assert "+135.00" in page  # Unrealized
    assert "10 Nov 2026" in page  # Price date


def test_no_price_bars_displays_no_price(logged_in_client, db):
    """Verify open positions display 'No price' and warning banner when prices are missing."""
    logged_in_client.post(
        "/portfolios/new",
        data={"name": "Unpriced Book", "currency": "MYR"},
    )
    p = db.portfolios.find_one({"name": "Unpriced Book"})
    p_id = str(p["_id"])

    # Add buy for a symbol with no price bars in DB
    logged_in_client.post(
        f"/portfolios/{p_id}/trades/new",
        data={
            "symbol": "DEMO4",
            "side": "buy",
            "qty": "100",
            "price": "5.0000",
            "fees": "8.00",
            "date": "2026-11-01",
            "version": 1,
        },
    )

    res = logged_in_client.get(f"/portfolios/{p_id}")
    assert res.status_code == 200
    page = res.data.decode("utf-8")

    assert "No price" in page
    assert "Prices could not be loaded" in page


def test_fees_api(client):
    """Verify GET /api/fees calculates Bursa and US educational estimates."""
    # Bursa estimate for 1000 shares @ RM 2.50
    res = client.get("/api/fees?symbol=DEMO1&side=buy&qty=1000&price=2.5000")
    assert res.status_code == 200
    data = res.get_json()
    assert data["currency"] == "MYR"
    assert "fees" in data
    assert "breakdown" in data
    assert "brokerage" in data["breakdown"]
    assert "clearing" in data["breakdown"]
    assert "stamp_duty" in data["breakdown"]

    # US fee estimate
    res = client.get("/api/fees?symbol=AAPL&side=buy&qty=10&price=150.0000")
    assert res.status_code == 200
    data = res.get_json()
    assert data["currency"] == "USD"
    assert "fees" in data

    # Validation errors
    assert client.get("/api/fees").status_code == 400
    assert client.get("/api/fees?symbol=DEMO1&side=invalid&qty=10&price=1.0").status_code == 400
    assert client.get("/api/fees?symbol=DEMO1&side=buy&qty=-5&price=1.0").status_code == 400
    assert client.get("/api/fees?symbol=DEMO1&side=buy&qty=10&price=-1.0").status_code == 400


def test_thousands_separators_and_formatting(logged_in_client, db):
    """Ensure money, prices, and shares format with thousands separators in templates."""
    bar_date = datetime(2026, 11, 10, 0, 0, 0, tzinfo=timezone.utc)
    prices.upsert_bars(
        db,
        "DEMO1",
        [
            {
                "symbol": "DEMO1",
                "date": bar_date,
                "open": Decimal("10.0000"),
                "high": Decimal("11.0000"),
                "low": Decimal("9.0000"),
                "close": Decimal("10.0000"),
                "volume": 50000,
            }
        ],
    )

    logged_in_client.post(
        "/portfolios/new",
        data={"name": "Big Book", "currency": "MYR"},
    )
    p = db.portfolios.find_one({"name": "Big Book"})
    p_id = str(p["_id"])

    # Buy 2,500 shares @ 8.0000 with 1,200.00 fees
    logged_in_client.post(
        f"/portfolios/{p_id}/trades/new",
        data={
            "symbol": "DEMO1",
            "side": "buy",
            "qty": "2500",
            "price": "8.0000",
            "fees": "1200.00",
            "date": "2026-11-01",
            "version": 1,
        },
    )

    # Sell 1,500 shares @ 12.0000 with 500.00 fees
    # Profit: 1500 * (12 - 8) - (720 buy fee + 500 sell fee) = 6000 - 1220 = +4,780.00
    logged_in_client.post(
        f"/portfolios/{p_id}/trades/new",
        data={
            "symbol": "DEMO1",
            "side": "sell",
            "qty": "1500",
            "price": "12.0000",
            "fees": "500.00",
            "date": "2026-11-05",
            "version": 2,
        },
    )

    res = logged_in_client.get(f"/portfolios/{p_id}")
    assert res.status_code == 200
    page = res.data.decode("utf-8")

    # Realized P/L must have comma separator
    assert "+4,780.00" in page
    # Shares must have comma separator
    assert "1,500" in page
    assert "1,000" in page  # remaining open shares
    assert "2,500" in page  # recorded buy trade shares
    # Fees must have comma separator
    assert "1,200.00" in page
    # Win rate has 1 decimal place
    assert "100.0%" in page

