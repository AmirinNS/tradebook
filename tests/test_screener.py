"""Tests for the stock screener module, database indexes, and routes."""

from datetime import date
from decimal import Decimal

import modules.prices as prices
import modules.screener as screener
import modules.synthetic as synthetic
import sources.money as money


def _seed_sample_universe(db):
    """Seed synthetic bars for DEMO symbols."""
    prices.ensure_indexes(db)
    screener.ensure_indexes(db)

    # Seed DEMO1 to DEMO5 with varying seeds and prices
    for i, sym in enumerate(["DEMO1", "DEMO2", "DEMO3", "DEMO4", "DEMO5"]):
        bars = synthetic.generate_ohlcv(
            symbol=sym,
            start=date(2025, 8, 18),
            sessions=250,
            seed=100 + i * 17,
            initial_price=f"{10 + i * 15}.0000",
        )
        prices.upsert_bars(db, sym, bars)

    return screener.build_snapshot(db)


def test_ensure_indexes(db):
    """Indexes on screener_snapshot should include sector, rsi, and unique symbol."""
    screener.ensure_indexes(db)
    indexes = db.screener_snapshot.index_information()

    assert "symbol_1" in indexes
    assert indexes["symbol_1"].get("unique") is True
    assert "sector_1" in indexes
    assert "rsi_1" in indexes


def test_build_snapshot_synthetic_data(db):
    """build_snapshot should compute metrics and persist Decimal128 for numerical queries."""
    count = _seed_sample_universe(db)
    assert count == 5

    # Check a stored snapshot document
    doc = db.screener_snapshot.find_one({"symbol": "DEMO1"})
    assert doc is not None
    assert doc["symbol"] == "DEMO1"
    assert doc["name"] == "Demo Apex Holdings"
    assert doc["sector"] == "Technology"
    assert doc["as_of_date"] is not None

    # Numbers stored as Decimal128
    assert isinstance(money.from_d128(doc["last_close"]), Decimal)
    assert isinstance(money.from_d128(doc["change"]), Decimal)
    assert isinstance(money.from_d128(doc["change_pct"]), Decimal)
    assert isinstance(money.from_d128(doc["rsi"]), Decimal)
    assert isinstance(money.from_d128(doc["sma50"]), Decimal)
    assert isinstance(money.from_d128(doc["sma200"]), Decimal)
    assert isinstance(doc["avg_volume_20"], int)
    assert isinstance(doc["above_sma200"], bool)
    assert isinstance(doc["macd_cross_up"], bool)


def test_build_snapshot_excludes_no_data(db):
    """Universe stocks without price bars should not be included in screener_snapshot."""
    _seed_sample_universe(db)

    # 1155.KL is in the universe but has no bars in the database
    doc = db.screener_snapshot.find_one({"symbol": "1155.KL"})
    assert doc is None

    # All items returned by run_screen must have data
    all_screened = screener.run_screen(db)
    assert len(all_screened) == 5
    for item in all_screened:
        assert item["last_close"] is not None
        assert item["symbol"].startswith("DEMO")


def test_filter_sector(db):
    """run_screen should filter by sector."""
    _seed_sample_universe(db)

    tech_results = screener.run_screen(db, {"sector": "Technology"})
    assert len(tech_results) >= 1
    assert all(item["sector"] == "Technology" for item in tech_results)

    energy_results = screener.run_screen(db, {"sector": "Energy"})
    assert len(energy_results) >= 1
    assert all(item["sector"] == "Energy" for item in energy_results)


def test_filter_rsi_lt_and_gt(db):
    """run_screen should filter by rsi_lt and rsi_gt numerically."""
    _seed_sample_universe(db)

    all_items = screener.run_screen(db)
    all_rsis = [item["rsi"] for item in all_items if item["rsi"] is not None]
    assert all_rsis, "Should have calculated RSIs"

    mid_rsi = sorted(all_rsis)[len(all_rsis) // 2]

    # Filter RSI below mid_rsi
    lt_results = screener.run_screen(db, {"rsi_lt": mid_rsi})
    assert len(lt_results) > 0
    assert all(item["rsi"] < mid_rsi for item in lt_results)

    # Filter RSI above mid_rsi
    gt_results = screener.run_screen(db, {"rsi_gt": mid_rsi})
    assert len(gt_results) > 0
    assert all(item["rsi"] > mid_rsi for item in gt_results)


def test_filter_above_sma200(db):
    """run_screen should filter by above_sma200 boolean flag."""
    _seed_sample_universe(db)

    above_results = screener.run_screen(db, {"above_sma200": True})
    for item in above_results:
        assert item["above_sma200"] is True
        assert item["last_close"] > item["sma200"]


def test_filter_macd_cross_up(db):
    """run_screen should filter by macd_cross_up boolean flag."""
    _seed_sample_universe(db)

    results = screener.run_screen(db, {"macd_cross_up": True})
    for item in results:
        assert item["macd_cross_up"] is True


def test_combined_filters(db):
    """run_screen should apply combined filters as a single MongoDB query."""
    _seed_sample_universe(db)

    results = screener.run_screen(
        db,
        {"sector": "Technology", "rsi_lt": Decimal(90), "rsi_gt": Decimal(10)},
    )
    for item in results:
        assert item["sector"] == "Technology"
        assert Decimal(10) < item["rsi"] < Decimal(90)


def test_sort_whitelist_and_direction(db):
    """run_screen should sort by whitelisted keys and default safely for unknown keys."""
    _seed_sample_universe(db)

    # Sort by last_close ascending
    by_close_asc = screener.run_screen(db, sort="last_close", direction="asc")
    closes = [item["last_close"] for item in by_close_asc]
    assert closes == sorted(closes)

    # Sort by last_close descending
    by_close_desc = screener.run_screen(db, sort="-last_close")
    closes_desc = [item["last_close"] for item in by_close_desc]
    assert closes_desc == sorted(closes, reverse=True)

    # Sort by rsi ascending
    by_rsi = screener.run_screen(db, sort="rsi", direction="asc")
    rsis = [item["rsi"] for item in by_rsi]
    assert rsis == sorted(rsis)

    # Unknown sort key should safely fallback to symbol ascending
    fallback_results = screener.run_screen(db, sort="malicious_unwhitelisted_key")
    symbols = [item["symbol"] for item in fallback_results]
    assert symbols == sorted(symbols)


def test_screener_route_get_unseeded(client, db):
    """GET /screener on an empty database should render successfully with 0 results."""
    screener.ensure_indexes(db)
    resp = client.get("/screener")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Screener" in html
    assert "No stocks match the selected criteria." in html


def test_screener_route_get_seeded(client, db):
    """GET /screener on a populated database shows results, as-of date, and filter controls."""
    _seed_sample_universe(db)

    resp = client.get("/screener")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Screener" in html
    assert "DEMO1" in html
    assert "DEMO2" in html
    assert "Technology" in html
    assert "Financial Services" in html
    assert "RSI below" in html
    assert "Above SMA200" in html
    assert "MACD cross up" in html
    assert "TODO" not in html


def test_screener_route_filter_rsi_lt(client, db):
    """GET /screener?rsi_lt=30 should return only rows with RSI under 30."""
    _seed_sample_universe(db)

    resp = client.get("/screener?rsi_lt=30")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Verify that any displayed stocks have RSI < 30
    items = screener.run_screen(db, {"rsi_lt": 30})
    for item in items:
        assert item["symbol"] in html


def test_screener_route_invalid_query_params_never_500(client, db):
    """Invalid query parameter types must yield friendly flash messages and never 500."""
    _seed_sample_universe(db)

    # Malformed RSI, unknown sector, arbitrary sort, bogus parameter
    bad_url = (
        "/screener?rsi_lt=not_a_number&rsi_gt=999&sector=Atlantis"
        "&sort=drop_table&dir=invalid_dir&unexpected_key=123"
    )
    resp = client.get(bad_url)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "Invalid RSI below" in html or "must be between" in html
    assert "Atlantis" in html
    assert "Invalid sort parameter" in html or "unexpected" in html.lower()


def test_navbar_includes_screener_link(client):
    """Navbar must include a link to Screener."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'href="/screener"' in html
    assert "Screener" in html
