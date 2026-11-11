"""Tests for modules.market_source using mocked yfinance responses."""

from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd

from modules.market_source import fetch_daily


def _make_sample_dataframe():
    """Create a sample pandas DataFrame mimicking yfinance.download output."""
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    data = {
        "Open": [150.0, 152.5, 151.0],
        "High": [153.0, 155.0, 152.0],
        "Low": [149.0, 151.0, 148.5],
        "Close": [152.0, 151.5, 149.0],
        "Volume": [1000000, 1200000, 950000],
    }
    return pd.DataFrame(data, index=dates)


def test_fetch_daily_normal(monkeypatch):
    """Verify normal bar parsing, types, and exact download arguments."""
    captured = {}

    def mock_download(symbol, **kwargs):
        captured["symbol"] = symbol
        captured["kwargs"] = kwargs
        return _make_sample_dataframe()

    monkeypatch.setattr("yfinance.download", mock_download)

    bars = fetch_daily("AAPL")

    assert captured["symbol"] == "AAPL"
    assert captured["kwargs"] == {
        "period": "2y",
        "interval": "1d",
        "auto_adjust": True,
        "multi_level_index": False,
        "progress": False,
        "timeout": 20,
    }

    assert len(bars) == 3
    first = bars[0]
    assert first["symbol"] == "AAPL"
    assert first["date"] == datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    assert isinstance(first["open"], Decimal)
    assert first["open"] == Decimal("150.0000")
    assert isinstance(first["high"], Decimal)
    assert first["high"] == Decimal("153.0000")
    assert isinstance(first["low"], Decimal)
    assert first["low"] == Decimal("149.0000")
    assert isinstance(first["close"], Decimal)
    assert first["close"] == Decimal("152.0000")
    assert isinstance(first["volume"], int)
    assert first["volume"] == 1000000


def test_fetch_daily_empty_dataframe(monkeypatch):
    """Verify empty DataFrame returns an empty list."""
    monkeypatch.setattr("yfinance.download", lambda *args, **kwargs: pd.DataFrame())
    assert fetch_daily("AAPL") == []


def test_fetch_daily_none_returned(monkeypatch):
    """Verify None from download returns an empty list."""
    monkeypatch.setattr("yfinance.download", lambda *args, **kwargs: None)
    assert fetch_daily("AAPL") == []


def test_fetch_daily_drops_nan_row(monkeypatch):
    """Verify rows with NaN values in any OHLCV column are dropped."""
    df = _make_sample_dataframe()
    # Introduce NaN in the second row's Close
    df.loc[df.index[1], "Close"] = float("nan")

    monkeypatch.setattr("yfinance.download", lambda *args, **kwargs: df)

    bars = fetch_daily("AAPL")
    assert len(bars) == 2
    assert bars[0]["date"] == datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    assert bars[1]["date"] == datetime(2024, 1, 4, 0, 0, 0, tzinfo=timezone.utc)


def test_fetch_daily_drops_non_finite_and_negative(monkeypatch):
    """Verify infinite, negative or zero prices/volumes are dropped."""
    df = _make_sample_dataframe()
    df.loc[df.index[0], "High"] = float("inf")
    df.loc[df.index[1], "Low"] = -5.0

    monkeypatch.setattr("yfinance.download", lambda *args, **kwargs: df)

    bars = fetch_daily("AAPL")
    assert len(bars) == 1
    assert bars[0]["date"] == datetime(2024, 1, 4, 0, 0, 0, tzinfo=timezone.utc)


def test_fetch_daily_catches_exception(monkeypatch):
    """Verify network or runtime exceptions are swallowed and return []."""
    def mock_download_raise(*args, **kwargs):
        raise ConnectionError("Network unreachable")

    monkeypatch.setattr("yfinance.download", mock_download_raise)

    # Must never raise into callers
    result = fetch_daily("AAPL")
    assert result == []


def test_fetch_daily_empty_symbol():
    """Verify empty or blank symbol string returns [] immediately."""
    assert fetch_daily("") == []
    assert fetch_daily("   ") == []
