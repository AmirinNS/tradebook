from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128

from sources.money import (
    as_decimal,
    from_d128,
    money,
    parse_decimal,
    price,
    to_d128,
    to_json,
)


def test_parse_decimal_accepts_numbers():
    assert parse_decimal("12.5") == Decimal("12.5")
    assert parse_decimal(" 7 ") == Decimal("7")
    assert parse_decimal("-0.0001") == Decimal("-0.0001")
    assert parse_decimal("0") == Decimal("0")
    assert parse_decimal("1e3") == Decimal("1E+3")


@pytest.mark.parametrize(
    "text",
    ["", "   ", "abc", "1,234.50", "nan", "NaN", "sNaN", "inf", "-Infinity", "Infinity"],
)
def test_parse_decimal_rejects_bad_input(text):
    with pytest.raises(ValueError):
        parse_decimal(text)


def test_parse_decimal_rejects_non_string():
    with pytest.raises(TypeError):
        parse_decimal(Decimal("1.5"))


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_as_decimal_rejects_non_finite(value):
    with pytest.raises(ValueError):
        as_decimal(value)


def test_as_decimal_rejects_float():
    with pytest.raises(TypeError):
        as_decimal(1.5)


def test_as_decimal_accepts_int_and_string():
    assert as_decimal(5) == Decimal("5")
    assert as_decimal("2.50") == Decimal("2.50")


def test_d128_round_trip_without_mongo():
    stored = to_d128(Decimal("1234.5678"))
    assert isinstance(stored, Decimal128)
    assert from_d128(stored) == Decimal("1234.5678")


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), float("inf")])
def test_to_d128_rejects_non_finite(value):
    with pytest.raises((ValueError, TypeError)):
        to_d128(value)


def test_from_d128_rejects_other_types():
    with pytest.raises(TypeError):
        from_d128(Decimal("1.5"))
    with pytest.raises(TypeError):
        from_d128(None)


def test_mongo_round_trip(db):
    amount = Decimal("9876.54")
    unit_price = Decimal("1.2345")
    db.money_roundtrip.insert_one(
        {"amount": to_d128(amount), "price": to_d128(unit_price)}
    )
    stored = db.money_roundtrip.find_one({})
    assert isinstance(stored["amount"], Decimal128)
    assert isinstance(stored["price"], Decimal128)
    assert from_d128(stored["amount"]) == amount
    assert from_d128(stored["price"]) == unit_price


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2.345", "2.35"),
        ("2.344", "2.34"),
        ("-2.345", "-2.35"),
        ("0.005", "0.01"),
        (5, "5.00"),
        ("3.1", "3.10"),
        ("2.999", "3.00"),
    ],
)
def test_money_rounds_half_up(value, expected):
    assert money(value) == Decimal(expected)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.23456", "1.2346"),
        ("1.23454", "1.2345"),
        ("-1.23455", "-1.2346"),
        (1, "1.0000"),
        ("0.00005", "0.0001"),
    ],
)
def test_price_rounds_half_up(value, expected):
    assert price(value) == Decimal(expected)


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity")])
def test_money_and_price_reject_non_finite(value):
    with pytest.raises(ValueError):
        money(value)
    with pytest.raises(ValueError):
        price(value)


def test_to_json_returns_decimal_string():
    rendered = to_json(Decimal("10.00"))
    assert rendered == "10.00"
    assert isinstance(rendered, str)
    assert to_json(money("2.345")) == "2.35"
    assert to_json(price("1.23456")) == "1.2346"
    assert to_json(Decimal("-0.5")) == "-0.5"


def test_to_json_rejects_non_finite():
    with pytest.raises(ValueError):
        to_json(Decimal("NaN"))
