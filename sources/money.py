"""Money helpers: the single place where Decimal meets Decimal128 and JSON.

Policy: Decimal on the Python side, Decimal128 for every persisted money field,
decimal strings in JSON. Prices keep 4 decimal places, money rounds to 2 places,
both with ROUND_HALF_UP. NaN and Infinity are rejected at every boundary.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from bson.decimal128 import Decimal128

MONEY_EXPONENT = Decimal("0.01")
PRICE_EXPONENT = Decimal("0.0001")


def parse_decimal(text):
    """Parse user input into a finite Decimal, rejecting empty, NaN and Infinity."""
    if not isinstance(text, str):
        raise TypeError("parse_decimal expects a string")
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Enter a number.")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"Enter a valid number, got {text!r}") from None
    if not value.is_finite():
        raise ValueError(f"Enter a finite number, got {text!r}")
    return value


def as_decimal(value):
    """Return value as a finite Decimal, rejecting NaN and Infinity."""
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        result = parse_decimal(value)
    else:
        raise TypeError(
            f"Expected a Decimal, int or numeric string, got {type(value).__name__}"
        )
    if not result.is_finite():
        raise ValueError(f"Value must be finite, got {value!r}")
    return result


def to_d128(value):
    """Convert a finite Decimal, int or numeric string to Decimal128 for storage."""
    return Decimal128(as_decimal(value))


def from_d128(value):
    """Read a stored Decimal128 money field back as a Decimal."""
    if not isinstance(value, Decimal128):
        raise TypeError(f"Expected a Decimal128, got {type(value).__name__}")
    return value.to_decimal()


def money(d):
    """Round a money amount to 2 decimal places, half up."""
    return as_decimal(d).quantize(MONEY_EXPONENT, rounding=ROUND_HALF_UP)


def price(d):
    """Round a price to 4 decimal places, half up."""
    return as_decimal(d).quantize(PRICE_EXPONENT, rounding=ROUND_HALF_UP)


def to_json(d):
    """Render a money or price value as a decimal string for JSON responses."""
    return str(as_decimal(d))
