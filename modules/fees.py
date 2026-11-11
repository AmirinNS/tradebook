"""Educational fee estimates. Stored user-confirmed actual fees take precedence."""

from decimal import ROUND_CEILING, Decimal

from sources.fee_schedule import (
    CLEARING_CAP,
    CLEARING_RATE,
    EXAMPLE_BROKERAGE_RATE,
    EXAMPLE_MIN_BROKERAGE,
    STAMP_CAP,
    STAMP_PER_UNIT,
    STAMP_UNIT,
)
from sources.money import as_decimal, money


def _contract_value(qty, price):
    if type(qty) is not int or qty <= 0:
        raise ValueError("Quantity must be a positive integer.")
    price = as_decimal(price)
    if price <= 0:
        raise ValueError("Price must be positive.")
    return Decimal(qty) * price


def _nonnegative(value):
    value = as_decimal(value)
    if value < 0:
        raise ValueError("Fee inputs cannot be negative.")
    return value


def estimate_bursa_fees(
    side, qty, price, brokerage_rate=EXAMPLE_BROKERAGE_RATE, min_brokerage=EXAMPLE_MIN_BROKERAGE
):
    """Estimate ordinary listed shares only, returning Decimal fee components.

    The default brokerage rate/minimum are an example, not a broker tariff.
    Contract value is unrounded when selecting the stamp-duty bracket.
    """
    if side not in ("buy", "sell"):
        raise ValueError("Side must be buy or sell.")
    contract_value = _contract_value(qty, price)
    rate = _nonnegative(brokerage_rate)
    minimum = _nonnegative(min_brokerage)
    brokerage = money(max(contract_value * rate, minimum))
    clearing = money(min(contract_value * CLEARING_RATE, CLEARING_CAP))
    stamp_units = (contract_value / STAMP_UNIT).to_integral_value(rounding=ROUND_CEILING)
    stamp_duty = money(min(stamp_units * STAMP_PER_UNIT, STAMP_CAP))
    # From 1 Oct 2025, 8% SST covers brokerage/clearing for REITs, ETFs,
    # rights and warrants only. Ordinary shares are not listed, so no SST here.
    sst = Decimal("0.00")
    return {
        "brokerage": brokerage,
        "clearing": clearing,
        "stamp_duty": stamp_duty,
        "sst": sst,
        "total": money(brokerage + clearing + stamp_duty + sst),
    }


def estimate_us_fees(qty, price, flat_fee):
    """Return a rounded flat educational estimate, independent of trade value."""
    _contract_value(qty, price)
    return money(_nonnegative(flat_fee))
