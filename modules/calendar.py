"""Realized P/L per trading day and the week grid used to render a calendar month."""

from calendar import Calendar
from collections import defaultdict
from decimal import Decimal

from sources.money import money


def daily_pnl(realized, year, month):
    """Return exit date -> realized P/L for one month, summed per day.

    Input is the realized portion list from pnl.fifo_positions: dicts holding an
    "exit" Trade whose date is UTC midnight for the exchange-local trading day,
    and a "pnl" already rounded to money. Only exits inside the given month are
    counted, so a caller never shows another month's totals. Days without an exit
    are absent; the caller fills them from month_grid. Values are Decimal at 2 dp,
    ordered by date.
    """
    totals = defaultdict(Decimal)
    for portion in realized:
        exit_day = portion["exit"].date.date()
        if (exit_day.year, exit_day.month) != (year, month):
            continue
        totals[exit_day] += portion["pnl"]
    return {day: money(total) for day, total in sorted(totals.items())}


def month_grid(year, month):
    """Return one month as a list of weeks, each week seven dates, Monday first.

    Leading and trailing days of the neighbouring months are included so every
    week is whole; the caller renders those dimmed. An out-of-range month or year
    raises ValueError from datetime.date.
    """
    return Calendar(firstweekday=0).monthdatescalendar(year, month)
