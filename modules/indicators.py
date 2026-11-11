"""Technical indicators over lists of Decimal closing prices.

Each function takes a list of Decimal and returns a list of the same length,
with None where the indicator has not warmed up yet. Nothing is rounded here:
callers quantize for display with sources.money.price or sources.money.money.
"""

from decimal import Decimal

RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

ZERO = Decimal(0)
ONE_HUNDRED = Decimal(100)


def _check_period(period):
    """Reject a non-positive period, which would divide by zero."""
    if period <= 0:
        raise ValueError("period must be positive")


def sma(values, period):
    """Simple moving average. None for the first period-1 values."""
    values = list(values)
    _check_period(period)
    result = [None] * len(values)
    if len(values) < period:
        return result
    window = sum(values[:period], ZERO)
    result[period - 1] = window / period
    for i in range(period, len(values)):
        window += values[i] - values[i - period]
        result[i] = window / period
    return result


def ema(values, period):
    """Exponential moving average seeded with the SMA of the first period values."""
    values = list(values)
    _check_period(period)
    result = [None] * len(values)
    if len(values) < period:
        return result
    factor = Decimal(2) / (period + 1)
    previous = sum(values[:period], ZERO) / period
    result[period - 1] = previous
    for i in range(period, len(values)):
        previous = (values[i] - previous) * factor + previous
        result[i] = previous
    return result


def _rsi_from_averages(avg_gain, avg_loss):
    """RSI from Wilder averages. A flat window is 50, gains with no loss are 100."""
    if avg_loss == 0:
        return ONE_HUNDRED if avg_gain > 0 else Decimal(50)
    return ONE_HUNDRED * avg_gain / (avg_gain + avg_loss)


def rsi(values, period=RSI_PERIOD):
    """Wilder RSI over `period` changes. None for the first period values.

    A flat window has no gain and no loss, so RSI is 50 by convention rather
    than undefined. A window with gains but no loss is 100.
    """
    values = list(values)
    _check_period(period)
    result = [None] * len(values)
    if len(values) <= period:
        return result
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    avg_gain = sum((c for c in changes[:period] if c > 0), ZERO) / period
    avg_loss = sum((-c for c in changes[:period] if c < 0), ZERO) / period
    result[period] = _rsi_from_averages(avg_gain, avg_loss)
    for i in range(period, len(changes)):
        change = changes[i]
        gain = change if change > 0 else ZERO
        loss = -change if change < 0 else ZERO
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        result[i + 1] = _rsi_from_averages(avg_gain, avg_loss)
    return result


def macd(values, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL):
    """Return (macd_line, signal_line, histogram) as lists of Decimal.

    The MACD line is ema(fast) minus ema(slow). The signal line is an EMA of the
    MACD line, seeded with the SMA of its first `signal` values. The histogram
    is the MACD line minus the signal line. Each list is None until it warms up.
    """
    values = list(values)
    _check_period(fast)
    _check_period(slow)
    _check_period(signal)
    fast_line = ema(values, fast)
    slow_line = ema(values, slow)
    line = [None] * len(values)
    for i in range(len(values)):
        if fast_line[i] is not None and slow_line[i] is not None:
            line[i] = fast_line[i] - slow_line[i]
    signal_line = [None] * len(values)
    start = max(fast, slow) - 1
    if len(values) > start:
        signal_line[start:] = ema(line[start:], signal)
    histogram = [None] * len(values)
    for i in range(len(values)):
        if signal_line[i] is not None:
            histogram[i] = line[i] - signal_line[i]
    return line, signal_line, histogram
