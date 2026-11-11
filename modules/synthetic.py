"""Deterministic synthetic OHLCV market data generator using Geometric Brownian Motion."""

import math
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sources.money import price

DEFAULT_INITIAL_PRICE = Decimal("25.0000")
DAILY_DRIFT = 0.0005
DAILY_VOLATILITY = 0.018


def _parse_start_date(start):
    """Normalize input start value to a datetime.date."""
    if isinstance(start, datetime):
        return start.date()
    if isinstance(start, date):
        return start
    if isinstance(start, str):
        return date.fromisoformat(start.strip())
    raise TypeError(f"Expected start as date, datetime or ISO string, got {type(start).__name__}")


def generate_ohlcv(symbol, start, sessions, seed=None, initial_price=None):
    """Generate deterministic weekday-only OHLCV bars using Geometric Brownian Motion.

    Args:
        symbol: Ticker symbol string (e.g. 'DEMO1').
        start: Starting date (date, datetime, or ISO string).
        sessions: Positive integer count of trading sessions to generate.
        seed: Random seed for deterministic generation.
        initial_price: Optional starting price (Decimal, string or int).

    Returns:
        List of bar dicts with keys: symbol, date (UTC midnight datetime),
        open (Decimal), high (Decimal), low (Decimal), close (Decimal), volume (int).
    """
    if sessions <= 0:
        raise ValueError("sessions must be a positive integer")

    clean_symbol = symbol.strip().upper()
    current_date = _parse_start_date(start)
    rng = random.Random(seed)

    start_price = (
        price(initial_price) if initial_price is not None else DEFAULT_INITIAL_PRICE
    )
    if start_price <= Decimal("0"):
        raise ValueError("initial_price must be positive")

    bars = []
    prev_close = start_price

    while len(bars) < sessions:
        # Weekdays only: 0 is Monday, 4 is Friday, 5 is Saturday, 6 is Sunday
        if current_date.weekday() < 5:
            bar_date = datetime(
                current_date.year,
                current_date.month,
                current_date.day,
                0,
                0,
                0,
                tzinfo=timezone.utc,
            )

            # Determine Open price
            if not bars:
                open_val = start_price
            else:
                # Small overnight gap
                gap = rng.gauss(0, 0.002)
                gap_factor = Decimal(str(round(1.0 + gap, 6)))
                open_val = max(Decimal("0.0100"), price(prev_close * gap_factor))

            # Intraday GBM return for Close price
            shock = rng.gauss(0, 1.0)
            drift_term = DAILY_DRIFT - 0.5 * (DAILY_VOLATILITY**2)
            log_ret = drift_term + DAILY_VOLATILITY * shock
            ret_factor = Decimal(str(round(math.exp(log_ret), 8)))
            close_val = max(Decimal("0.0100"), price(open_val * ret_factor))

            # High and Low wiggles
            high_wiggle = abs(rng.gauss(0, 0.006))
            low_wiggle = abs(rng.gauss(0, 0.006))

            high_candidate = price(
                max(open_val, close_val) * Decimal(str(round(1.0 + high_wiggle, 6)))
            )
            low_candidate = price(
                min(open_val, close_val) * Decimal(str(round(1.0 - low_wiggle, 6)))
            )

            high_val = max(high_candidate, open_val, close_val)
            low_val = max(Decimal("0.0001"), min(low_candidate, open_val, close_val))

            # Realistic trading volume
            volume = max(1000, int(rng.lognormvariate(11.5, 0.4)))

            bars.append(
                {
                    "symbol": clean_symbol,
                    "date": bar_date,
                    "open": open_val,
                    "high": high_val,
                    "low": low_val,
                    "close": close_val,
                    "volume": volume,
                }
            )
            prev_close = close_val

        current_date += timedelta(days=1)

    return bars
