from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from modules.calendar import daily_pnl, month_grid
from modules.ledger import Trade
from modules.pnl import fifo_positions


def trade(side, qty, price="10", fees="0.00", day=1, seq=0, symbol="DEMO1"):
    return Trade(
        "portfolio",
        symbol,
        side,
        qty,
        Decimal(price),
        Decimal(fees),
        datetime(2026, 1, day, tzinfo=timezone.utc),
        seq,
    )


def portion(day, pnl, month=1, symbol="DEMO1"):
    sell = Trade(
        "portfolio",
        symbol,
        "sell",
        1,
        Decimal("10"),
        Decimal("0.00"),
        datetime(2026, month, day, tzinfo=timezone.utc),
        1,
    )
    return {"exit": sell, "pnl": Decimal(pnl)}


def test_daily_pnl_sums_realized_pnl_by_exit_date():
    realized = [portion(5, "10.05"), portion(5, "-2.50"), portion(8, "1.00")]
    assert daily_pnl(realized, 2026, 1) == {
        date(2026, 1, 5): Decimal("7.55"),
        date(2026, 1, 8): Decimal("1.00"),
    }


def test_daily_pnl_only_reports_the_requested_month():
    realized = [portion(28, "4.00"), portion(3, "9.00", month=2)]
    assert daily_pnl(realized, 2026, 1) == {date(2026, 1, 28): Decimal("4.00")}
    assert daily_pnl(realized, 2026, 2) == {date(2026, 2, 3): Decimal("9.00")}
    assert daily_pnl(realized, 2026, 3) == {}


def test_daily_pnl_of_no_closed_portions_is_empty():
    assert daily_pnl([], 2026, 1) == {}


def test_daily_pnl_totals_are_money_decimals():
    totals = daily_pnl([portion(6, "1.1"), portion(6, "2.2")], 2026, 1)
    assert list(totals) == [date(2026, 1, 6)]
    assert str(totals[date(2026, 1, 6)]) == "3.30"


def test_daily_pnl_agrees_with_fifo_positions_output():
    rows = [trade("buy", 10), trade("sell", 4, price="12", day=6, seq=1),
            trade("sell", 6, price="9", day=9, seq=2)]
    _, realized = fifo_positions(rows)
    assert daily_pnl(realized, 2026, 1) == {
        date(2026, 1, 6): Decimal("8.00"),
        date(2026, 1, 9): Decimal("-6.00"),
    }


def test_month_grid_is_whole_weeks_starting_on_monday():
    weeks = month_grid(2026, 2)
    assert len(weeks) == 5
    assert all(len(week) == 7 for week in weeks)
    assert weeks[0] == [
        date(2026, 1, 26),
        date(2026, 1, 27),
        date(2026, 1, 28),
        date(2026, 1, 29),
        date(2026, 1, 30),
        date(2026, 1, 31),
        date(2026, 2, 1),
    ]
    assert weeks[-1][-1] == date(2026, 3, 1)


def test_month_grid_covers_every_day_of_the_month():
    for year, month, days in ((2026, 2, 28), (2028, 2, 29), (2026, 4, 30), (2026, 12, 31)):
        shown = [day for week in month_grid(year, month) for day in week if
                 (day.year, day.month) == (year, month)]
        assert shown == [date(year, month, day) for day in range(1, days + 1)]


def test_month_grid_adds_no_padding_when_the_month_starts_on_monday():
    assert month_grid(2026, 6)[0] == [date(2026, 6, day) for day in range(1, 8)]


def test_month_grid_spans_the_year_boundary():
    weeks = month_grid(2026, 12)
    assert weeks[0][0] == date(2026, 11, 30)
    assert weeks[-1][-1] == date(2027, 1, 3)


@pytest.mark.parametrize("month", [0, 13])
def test_month_grid_rejects_an_out_of_range_month(month):
    with pytest.raises(ValueError):
        month_grid(2026, month)
