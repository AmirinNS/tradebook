import random
from decimal import Decimal

import pytest

from modules.indicators import ema, macd, rsi, sma
from sources.money import price


def dec(text):
    """Shorten Decimal literals in the hand-computed cases below."""
    return Decimal(text)


def test_sma_warm_up_and_values():
    values = [dec("1"), dec("2"), dec("3"), dec("4"), dec("5")]
    assert sma(values, 3) == [None, None, dec("2"), dec("3"), dec("4")]


def test_sma_rolling_window_matches_manual_sum():
    values = [dec("10.5"), dec("11.25"), dec("9.75"), dec("12.00"), dec("8.50")]
    # (10.50 + 11.25 + 9.75) / 3 = 31.50 / 3 = 10.50
    # (11.25 + 9.75 + 12.00) / 3 = 33.00 / 3 = 11.00
    # (9.75 + 12.00 + 8.50) / 3 = 30.25 / 3 = 10.0833...
    result = sma(values, 3)
    assert result[2] == dec("10.5")
    assert result[3] == dec("11")
    assert price(result[4]) == dec("10.0833")


def test_sma_empty_and_short_input():
    assert sma([], 3) == []
    assert sma([dec("1")], 3) == [None]
    assert sma([dec("1"), dec("2")], 3) == [None, None]


def test_sma_rejects_non_positive_period():
    with pytest.raises(ValueError):
        sma([dec("1")], 0)


def test_ema_seed_and_recurrence_exact():
    values = [dec("10"), dec("20"), dec("30"), dec("40"), dec("50")]
    # seed = (10 + 20 + 30) / 3 = 20; factor = 2 / (3 + 1) = 0.5
    # ema[3] = (40 - 20) * 0.5 + 20 = 30
    # ema[4] = (50 - 30) * 0.5 + 30 = 40
    assert ema(values, 3) == [None, None, dec("20"), dec("30"), dec("40")]


def test_ema_empty_and_short_input():
    assert ema([], 4) == []
    assert ema([dec("1"), dec("2"), dec("3")], 4) == [None, None, None]


def test_functions_do_not_mutate_input():
    values = [dec("1"), dec("2"), dec("3")]
    sma(values, 2)
    ema(values, 2)
    rsi(values, 2)
    macd(values, 2, 3, 2)
    assert values == [dec("1"), dec("2"), dec("3")]


def test_rsi_wilder_period_two_exact():
    # changes: +2, +2, -2, +2 over 100 -> 102 -> 104 -> 102 -> 104
    values = [dec("100"), dec("102"), dec("104"), dec("102"), dec("104")]
    # avg_gain = 2, avg_loss = 0 -> 100
    # avg_gain = (2 * 1 + 0) / 2 = 1, avg_loss = (0 * 1 + 2) / 2 = 1 -> 50
    # avg_gain = (1 * 1 + 2) / 2 = 1.5, avg_loss = (1 * 1 + 0) / 2 = 0.5 -> 75
    assert rsi(values, 2) == [None, None, dec("100"), dec("50"), dec("75")]


def test_rsi_default_period_warm_up_and_all_gains():
    values = [dec(str(100 + i)) for i in range(20)]
    result = rsi(values)
    assert result[:14] == [None] * 14
    # every change is a gain of 1, so avg_loss stays 0 and RSI stays 100
    assert result[14:] == [dec("100")] * 6


def test_rsi_flat_window_is_fifty():
    values = [dec("50")] * 20
    result = rsi(values)
    assert result[:14] == [None] * 14
    # a flat window has no gain and no loss, so RSI is 50 by convention
    assert result[14:] == [dec("50")] * 6


def test_rsi_all_losses_is_zero():
    values = [dec(str(200 - i)) for i in range(20)]
    result = rsi(values)
    assert result[14:] == [dec("0")] * 6


def test_rsi_default_period_mixed_case():
    # 4 gains of 49 then 10 losses of 8.4, then a loss of 6
    values = [dec("100")]
    for _ in range(4):
        values.append(values[-1] + dec("49"))
    for _ in range(10):
        values.append(values[-1] - dec("8.4"))
    values.append(values[-1] - dec("6"))
    result = rsi(values)
    assert result[:14] == [None] * 14
    # first 14 changes: avg_gain = 196 / 14 = 14, avg_loss = 84 / 14 = 6
    # RSI = 100 * 14 / (14 + 6) = 70
    assert result[14] == dec("70")
    # next change: avg_gain = (14 * 13 + 0) / 14 = 13, avg_loss = (6 * 13 + 6) / 14 = 6
    # RSI = 100 * 13 / 19 = 68.421052...
    assert result[15] == pytest.approx(dec("68.421052631579"), abs=dec("0.0000000001"))


def test_rsi_stays_within_bounds():
    rng = random.Random(7)
    values = [price(dec(str(rng.uniform(1, 50)))) for _ in range(200)]
    result = rsi(values)
    assert len(result) == len(values)
    for value in result[14:]:
        assert dec("0") <= value <= dec("100")


def test_rsi_empty_and_short_input():
    assert rsi([], 14) == []
    assert rsi([dec("1"), dec("2")], 14) == [None, None]
    assert rsi([dec("1"), dec("2")], 2) == [None, None]


def test_macd_default_warm_up_and_seed_value():
    values = [dec(str(10 + i)) for i in range(60)]
    line, signal_line, histogram = macd(values)
    assert line[:25] == [None] * 25
    # On a unit ramp both EMAs sit at their steady-state lag, which is also the
    # lag of their seed: ema12 lags by (13 - 1) / 2 = 5.5 and ema26 by
    # (27 - 1) / 2 = 12.5, so the MACD line is the constant 12.5 - 5.5 = 7
    # from its first warm index onwards.
    assert line[25:] == [dec("7")] * 35
    assert signal_line[:33] == [None] * 33
    assert signal_line[33:] == [dec("7")] * 27
    assert histogram[:33] == [None] * 33
    assert histogram[33:] == [dec("0")] * 27


def test_macd_default_periods_react_to_a_spike():
    values = [dec(str(10 + i)) for i in range(59)] + [dec("100")]
    line, signal_line, histogram = macd(values)
    # the ramp keeps the MACD line at 7 up to the spike
    assert line[25:59] == [dec("7")] * 34
    # ema12[59] = (11 / 13) * 62.5 + (2 / 13) * 100 = 887.5 / 13
    # ema26[59] = (25 / 27) * 55.5 + (2 / 27) * 100 = 1587.5 / 27
    # macd[59] = 887.5 / 13 - 1587.5 / 27 = 3325 / 351 = 9.4729344729...
    assert line[59] == pytest.approx(dec("9.4729344729"), abs=dec("0.000000001"))
    # the signal line is still 7 before the spike: 7 + 0.2 * (macd - 7)
    assert signal_line[59] == pytest.approx(dec("7.4945868946"), abs=dec("0.000000001"))
    assert histogram[59] == pytest.approx(dec("1.9783475783"), abs=dec("0.000000001"))


def test_macd_flat_series_is_zero():
    values = [dec("7.25")] * 40
    line, signal_line, histogram = macd(values)
    assert line[25:] == [dec("0")] * 15
    assert signal_line[33:] == [dec("0")] * 7
    assert histogram[33:] == [dec("0")] * 7


def test_macd_small_periods_hand_computed():
    values = [dec(x) for x in "10 11 12 13 14 15 16 17 18 19 25".split()]
    line, signal_line, histogram = macd(values, fast=3, slow=9, signal=3)
    # ema3: seed (10+11+12)/3 = 11, factor 0.5 -> 12, 13, 14, 15, 16, 17, 18, 21.5
    # ema9: seed (10+..+18)/9 = 14, factor 0.2 -> 15, 17
    assert line[:8] == [None] * 8
    assert line[8:] == [dec("3"), dec("3"), dec("4.5")]
    # signal = mean of the first three MACD values = (3 + 3 + 4.5) / 3 = 3.5
    assert signal_line[:10] == [None] * 10
    assert signal_line[10:] == [dec("3.5")]
    assert histogram[:10] == [None] * 10
    assert histogram[10:] == [dec("1.0")]


def test_macd_empty_input():
    assert macd([], 3, 9, 3) == ([], [], [])
    assert macd([dec("1"), dec("2")], 3, 9, 3) == ([None, None], [None, None], [None, None])


def test_macd_rejects_non_positive_periods():
    values = [dec(str(i)) for i in range(40)]
    with pytest.raises(ValueError):
        macd(values, 0, 9, 3)
    with pytest.raises(ValueError):
        macd(values, 3, 0, 3)
    with pytest.raises(ValueError):
        macd(values, 3, 9, 0)


def test_indicators_preserve_length():
    values = [dec(str(i)) for i in range(40)]
    assert len(sma(values, 5)) == 40
    assert len(ema(values, 5)) == 40
    assert len(rsi(values, 14)) == 40
    for series in macd(values):
        assert len(series) == 40
