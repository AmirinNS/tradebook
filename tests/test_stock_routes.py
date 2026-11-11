"""Integration tests for stock routes and technical chart API."""

from datetime import date
from decimal import Decimal

import modules.prices as prices
import modules.synthetic as synthetic
import sources.universe as universe


def test_index_landing_page(client):
    """GET / should render the product landing page with link to stocks."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "tradebook" in html
    assert "/stocks" in html
    assert "Browse the latest items" not in html


def test_stocks_index_unseeded(client, db):
    """GET /stocks with empty price store should show universe with 'No price' state."""
    resp = client.get("/stocks")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "DEMO1" in html
    assert "1155.KL" in html
    assert "AAPL" in html
    assert "No price" in html


def test_stocks_index_seeded(client, db):
    """GET /stocks with seeded bars should show price, change, and formatted date."""
    bars = synthetic.generate_ohlcv("DEMO1", start=date(2026, 1, 1), sessions=10, seed=42)
    prices.upsert_bars(db, bars)

    resp = client.get("/stocks")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "DEMO1" in html
    assert "No price" not in html.split("DEMO1")[1].split("</tr>")[0]


def test_stock_detail_unknown_symbol_404(client):
    """GET /stocks/<unknown> should return 404."""
    resp = client.get("/stocks/NONEXISTENT999")
    assert resp.status_code == 404


def test_stock_detail_unseeded(client, db):
    """GET /stocks/<symbol> without price data shows 'No price data' alert."""
    resp = client.get("/stocks/DEMO1")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "DEMO1" in html
    assert "No price data for this symbol yet." in html


def test_stock_detail_seeded(client, db):
    """GET /stocks/<symbol> with seeded bars displays quote, chart panes, and attribution."""
    bars = synthetic.generate_ohlcv("DEMO1", start=date(2026, 1, 1), sessions=50, seed=42)
    prices.upsert_bars(db, bars)

    resp = client.get("/stocks/demo1")  # test case insensitivity
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "DEMO1" in html
    assert "priceChart" in html
    assert "rsiChart" in html
    assert "macdChart" in html
    assert "TradingView Lightweight Charts" in html
    assert "https://www.tradingview.com/" in html
    assert "Synthetic demo" in html


def test_api_stock_bars_unknown_symbol_404(client):
    """GET /api/stocks/<unknown>/bars returns 404 JSON."""
    resp = client.get("/api/stocks/NONEXISTENT999/bars")
    assert resp.status_code == 404
    assert resp.is_json
    data = resp.get_json()
    assert "error" in data


def test_api_stock_bars_unseeded(client, db):
    """GET /api/stocks/<symbol>/bars with no data returns empty bars list."""
    resp = client.get("/api/stocks/DEMO2/bars")
    assert resp.status_code == 200
    assert resp.is_json
    data = resp.get_json()
    assert data["symbol"] == "DEMO2"
    assert data["bars"] == []


def test_api_stock_bars_json_shape_and_string_prices(client, db):
    """GET /api/stocks/<symbol>/bars returns bars with decimal string prices and indicators."""
    bars = synthetic.generate_ohlcv("DEMO1", start=date(2026, 1, 1), sessions=60, seed=123)
    prices.upsert_bars(db, bars)

    resp = client.get("/api/stocks/DEMO1/bars")
    assert resp.status_code == 200
    assert resp.is_json
    data = resp.get_json()

    assert data["symbol"] == "DEMO1"
    bar_list = data["bars"]
    assert len(bar_list) == 60

    for bar in bar_list:
        # Time format is YYYY-MM-DD
        assert len(bar["time"]) == 10
        assert bar["time"][4] == "-" and bar["time"][7] == "-"

        # Prices must be strings (no floats across the wire)
        assert isinstance(bar["open"], str)
        assert isinstance(bar["high"], str)
        assert isinstance(bar["low"], str)
        assert isinstance(bar["close"], str)
        assert isinstance(bar["volume"], int)

        # Decimal parseable
        Decimal(bar["open"])
        Decimal(bar["high"])
        Decimal(bar["low"])
        Decimal(bar["close"])

    # Indicators warm up properly
    # SMA20 warms up at index 19 (the 20th bar)
    assert bar_list[0]["sma20"] is None
    assert bar_list[18]["sma20"] is None
    assert isinstance(bar_list[19]["sma20"], str)
    Decimal(bar_list[19]["sma20"])

    # SMA50 warms up at index 49 (the 50th bar)
    assert bar_list[48]["sma50"] is None
    assert isinstance(bar_list[49]["sma50"], str)
    Decimal(bar_list[49]["sma50"])

    # RSI14 warms up at index 14 (15th bar)
    assert bar_list[0]["rsi"] is None
    assert bar_list[13]["rsi"] is None
    assert isinstance(bar_list[14]["rsi"], str)
    Decimal(bar_list[14]["rsi"])

    # MACD warms up
    assert isinstance(bar_list[-1]["macd"], str)
    assert isinstance(bar_list[-1]["macd_signal"], str)
    assert isinstance(bar_list[-1]["macd_hist"], str)


def test_all_universe_symbols_route(client, db):
    """All symbols in UNIVERSE can be loaded without 500 error."""
    for symbol in universe.ALL_SYMBOLS:
        resp = client.get(f"/stocks/{symbol}")
        assert resp.status_code == 200
