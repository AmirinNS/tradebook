"""Ordinary listed share fee schedule supplied by the Phase C review.

These are estimates for prefilling a form. Confirmed actual fees are authoritative.
"""

from decimal import Decimal

EFFECTIVE_DATE = "checked 2026-11-11"
SOURCE_URL = "https://www.rakutentrade.my/fees"
CLEARING_RATE = Decimal("0.0003")
CLEARING_CAP = Decimal("1000.00")
STAMP_UNIT = Decimal("1000.00")
STAMP_PER_UNIT = Decimal("1.00")
STAMP_CAP = Decimal("1000.00")
# Broker-specific example, not an exchange rule: 0.10% with an RM2.88 minimum.
EXAMPLE_BROKERAGE_RATE = Decimal("0.001")
EXAMPLE_MIN_BROKERAGE = Decimal("2.88")
