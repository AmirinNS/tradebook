"""Market data provider adapter using yfinance.

This is the only module in the application permitted to import yfinance.
Bars returned are split- and dividend-adjusted. Dates are normalized to the
exchange-local day at UTC midnight. Non-finite rows are dropped. Errors are
caught and logged; this module never raises into callers.
"""

import logging
import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import pandas as pd
import yfinance

from sources.money import price

logger = logging.getLogger(__name__)


def _is_finite_number(val):
    """Return True if val is a non-null, finite number."""
    if val is None or pd.isna(val):
        return False
    try:
        num = float(val)
        return not (math.isnan(num) or math.isinf(num))
    except (TypeError, ValueError):
        return False


def fetch_daily(symbol):
    """Fetch 2 years of daily split/dividend-adjusted OHLCV bars for symbol.

    Args:
        symbol: Ticker symbol string (e.g. 'AAPL' or '1155.KL').

    Returns:
        List of bar dicts with keys: symbol, date (UTC midnight datetime),
        open (Decimal), high (Decimal), low (Decimal), close (Decimal), volume (int).
        Returns an empty list on failure, timeout, or missing data. Never raises.
    """
    clean_symbol = symbol.strip().upper() if symbol else ""
    if not clean_symbol:
        return []

    try:
        df = yfinance.download(
            clean_symbol,
            period="2y",
            interval="1d",
            auto_adjust=True,
            multi_level_index=False,
            progress=False,
            timeout=20,
        )

        if df is None or df.empty:
            logger.info("No daily bars returned for %s", clean_symbol)
            return []

        # Find expected columns case-insensitively
        col_map = {str(c).strip().lower(): c for c in df.columns}
        required = ["open", "high", "low", "close", "volume"]
        if not all(col in col_map for col in required):
            logger.warning(
                "Missing required OHLCV columns for %s in %s",
                clean_symbol,
                list(df.columns),
            )
            return []

        open_col = col_map["open"]
        high_col = col_map["high"]
        low_col = col_map["low"]
        close_col = col_map["close"]
        vol_col = col_map["volume"]

        bars = []
        for idx, row in df.iterrows():
            raw_open = row[open_col]
            raw_high = row[high_col]
            raw_low = row[low_col]
            raw_close = row[close_col]
            raw_vol = row[vol_col]

            # Drop rows with non-finite values
            if not (
                _is_finite_number(raw_open)
                and _is_finite_number(raw_high)
                and _is_finite_number(raw_low)
                and _is_finite_number(raw_close)
                and _is_finite_number(raw_vol)
            ):
                continue

            try:
                dec_open = Decimal(str(raw_open))
                dec_high = Decimal(str(raw_high))
                dec_low = Decimal(str(raw_low))
                dec_close = Decimal(str(raw_close))
            except (InvalidOperation, TypeError, ValueError):
                continue

            if not (
                dec_open.is_finite()
                and dec_high.is_finite()
                and dec_low.is_finite()
                and dec_close.is_finite()
            ):
                continue

            if dec_open <= 0 or dec_high <= 0 or dec_low <= 0 or dec_close <= 0:
                continue

            vol_int = int(float(raw_vol))
            if vol_int < 0:
                continue

            # Exchange-local day normalized to UTC midnight
            local_date = idx.date() if hasattr(idx, "date") else idx
            bar_date = datetime(
                local_date.year,
                local_date.month,
                local_date.day,
                0,
                0,
                0,
                tzinfo=timezone.utc,
            )

            p_open = price(dec_open)
            p_close = price(dec_close)
            p_high = max(price(dec_high), p_open, p_close)
            p_low = max(Decimal("0.0001"), min(price(dec_low), p_open, p_close))

            bars.append(
                {
                    "symbol": clean_symbol,
                    "date": bar_date,
                    "open": p_open,
                    "high": p_high,
                    "low": p_low,
                    "close": p_close,
                    "volume": vol_int,
                }
            )

        return bars

    except Exception as exc:
        logger.warning("Failed to fetch daily bars for %s: %s", clean_symbol, exc)
        return []
