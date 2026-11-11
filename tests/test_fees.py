from decimal import Decimal

import pytest

from modules.fees import estimate_bursa_fees, estimate_us_fees
from sources.fee_schedule import EFFECTIVE_DATE, SOURCE_URL


def test_schedule_is_dated_and_cites_verified_source():
    assert EFFECTIVE_DATE == "checked 2026-11-11"
    assert SOURCE_URL == "https://www.rakutentrade.my/fees"


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize(
    "value,stamp",
    [
        ("999.99", "1.00"),
        ("1000.00", "1.00"),
        ("1000.01", "2.00"),
        ("2000.00", "2.00"),
        ("2000.01", "3.00"),
    ],
)
def test_stamp_duty_thresholds(side, value, stamp):
    assert estimate_bursa_fees(side, 1, Decimal(value))["stamp_duty"] == Decimal(stamp)


def test_four_decimal_price_is_not_rounded_before_stamp_threshold():
    assert estimate_bursa_fees("buy", 1, Decimal("1000.0001"))["stamp_duty"] == Decimal("2.00")


def test_minimum_brokerage_and_no_sst_for_ordinary_shares():
    fees = estimate_bursa_fees("buy", 100, Decimal("1.00"))
    assert fees == {
        "brokerage": Decimal("2.88"),
        "clearing": Decimal("0.03"),
        "stamp_duty": Decimal("1.00"),
        "sst": Decimal("0.00"),
        "total": Decimal("3.91"),
    }
    assert all(isinstance(value, Decimal) for value in fees.values())


def test_brokerage_is_configurable_and_percentage_exceeds_minimum():
    fees = estimate_bursa_fees("sell", 1000, Decimal("10"), Decimal("0.002"), Decimal("5"))
    assert fees["brokerage"] == Decimal("20.00")
    assert fees["clearing"] == Decimal("3.00")
    assert fees["stamp_duty"] == Decimal("10.00")
    assert fees["total"] == Decimal("33.00")


@pytest.mark.parametrize(
    "contract_value,clearing,stamp",
    [
        ("999000", "299.70", "999.00"),
        ("1000000", "300.00", "1000.00"),
        ("1000000.01", "300.00", "1000.00"),
        ("3333333.33", "1000.00", "1000.00"),
        ("4000000", "1000.00", "1000.00"),
    ],
)
def test_clearing_and_stamp_caps(contract_value, clearing, stamp):
    fees = estimate_bursa_fees("buy", 1, Decimal(contract_value), Decimal(0), Decimal(0))
    assert fees["clearing"] == Decimal(clearing)
    assert fees["stamp_duty"] == Decimal(stamp)
    assert fees["total"] == Decimal(clearing) + Decimal(stamp)


def test_fee_components_round_half_up():
    fees = estimate_bursa_fees("buy", 1, Decimal("50"), Decimal("0.0001"), Decimal(0))
    assert fees["brokerage"] == Decimal("0.01")
    assert fees["clearing"] == Decimal("0.02")


def test_us_is_a_flat_educational_estimate():
    assert estimate_us_fees(1, Decimal("1"), Decimal("2.345")) == Decimal("2.35")
    assert estimate_us_fees(1000, Decimal("100"), Decimal("2.345")) == Decimal("2.35")
    assert estimate_us_fees(1, Decimal("1"), Decimal("0")) == Decimal("0.00")


@pytest.mark.parametrize(
    "qty,price",
    [
        (0, "1"),
        (-1, "1"),
        (True, "1"),
        (1.5, "1"),
        (1, "0"),
        (1, "-1"),
        (1, "NaN"),
        (1, "Infinity"),
    ],
)
def test_both_estimators_reject_invalid_contracts(qty, price):
    with pytest.raises(ValueError):
        estimate_bursa_fees("buy", qty, Decimal(price))
    with pytest.raises(ValueError):
        estimate_us_fees(qty, Decimal(price), Decimal(0))


@pytest.mark.parametrize("field", ["brokerage_rate", "min_brokerage"])
@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity"])
def test_invalid_brokerage_inputs(field, value):
    with pytest.raises(ValueError):
        estimate_bursa_fees("buy", 1, Decimal("1"), **{field: Decimal(value)})


def test_invalid_side_flat_fee_and_float_money():
    with pytest.raises(ValueError):
        estimate_bursa_fees("short", 1, Decimal("1"))
    for value in ("-1", "NaN", "Infinity"):
        with pytest.raises(ValueError):
            estimate_us_fees(1, Decimal("1"), Decimal(value))
    with pytest.raises(TypeError):
        estimate_bursa_fees("buy", 1, 1.5)
    with pytest.raises(TypeError):
        estimate_us_fees(1, Decimal("1"), 1.5)
