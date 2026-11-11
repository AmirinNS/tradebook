"""Shared trading journal contract.

A portfolio has user_id, name, currency (MYR/USD), and integer version. It has
one currency. Known-symbol currencies must match it; free-text symbols use it.
A Trade has portfolio_id, uppercase symbol, buy/sell side, positive integer
qty, Decimal price (4 places), Decimal actual fees (2 places), UTC-midnight
date for the exchange-local trading day, integer seq assigned on insert,
manual/csv/pdf source, and optional import_id. Persistence converts price/fees
to Decimal128 only through sources.money; JSON uses decimal strings.

Positions are long only and FIFO ordered by (date, seq) within each symbol.
Actual fees are authoritative. Allocate fees by quantity, retaining unallocated
buy fees with the open remainder and giving the last allocation the remainder.
A statistical trade is one closed lot portion. Break-even is neither win nor
loss; profit factor is None with no losses, win rate None with no portions.

Every add, edit, delete, and import confirmation must validate the complete
proposed history of affected symbols through pnl.fifo_positions before saving.
Writes claim the portfolio with update_one({_id, user_id, version: v},
{$inc: {version: 1}}); no match means HTTP 409. Shortcut: this optimistic lock
is sufficient for one host; a crash before the trade write only bumps version.
"""

import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sources.money import money, price
from sources.universe import get_symbol_info


@dataclass(frozen=True)
class Trade:
    portfolio_id: object
    symbol: str
    side: str
    qty: int
    price: Decimal
    fees: Decimal
    date: datetime
    seq: int
    source: str = "manual"
    import_id: object | None = None


def validate_trade(trade, portfolio_currency):
    """Return an unchanged valid Trade, or raise ValueError at the input boundary."""
    if portfolio_currency not in ("MYR", "USD"):
        raise ValueError("Portfolio currency must be MYR or USD.")
    if not isinstance(trade, Trade):
        raise ValueError("Expected a Trade record.")
    if not trade.portfolio_id:
        raise ValueError("A portfolio is required.")
    if not isinstance(trade.symbol, str) or not re.fullmatch(
        r"[A-Z0-9][A-Z0-9.-]{0,31}", trade.symbol
    ):
        raise ValueError("Symbol must be an uppercase ticker of at most 32 characters.")
    info = get_symbol_info(trade.symbol)
    if info and info["currency"] != portfolio_currency:
        raise ValueError("Trade currency must match the portfolio currency.")
    if trade.side not in ("buy", "sell"):
        raise ValueError("Side must be buy or sell.")
    if type(trade.qty) is not int or trade.qty <= 0:
        raise ValueError("Quantity must be a positive integer.")
    for name, value, round_value, positive in (
        ("Price", trade.price, price, True),
        ("Fees", trade.fees, money, False),
    ):
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError(f"{name} must be a finite Decimal.")
        if value < 0 or (positive and value == 0) or value != round_value(value):
            raise ValueError(f"{name} has an invalid amount or precision.")
    if (
        not isinstance(trade.date, datetime)
        or trade.date.utcoffset() != timedelta(0)
        or any((trade.date.hour, trade.date.minute, trade.date.second, trade.date.microsecond))
    ):
        raise ValueError("Trade date must be UTC midnight.")
    if type(trade.seq) is not int or trade.seq < 0:
        raise ValueError("Sequence must be a non-negative integer.")
    if trade.source not in ("manual", "csv", "pdf"):
        raise ValueError("Source must be manual, csv or pdf.")
    return trade


def order_trades(trades):
    """Return a new list sorted by trading day, then the assigned sequence."""
    return sorted(trades, key=lambda trade: (trade.date, trade.seq))


def group_by_symbol(trades):
    """Return symbol -> ordered Trade lists, preserving first-seen symbol order."""
    groups = {}
    for trade in trades:
        groups.setdefault(trade.symbol, []).append(trade)
    return {symbol: order_trades(rows) for symbol, rows in groups.items()}


def _fee_portion(total, qty, total_qty, remaining, is_last):
    if is_last:
        return remaining
    # Half-up shares can exhaust a tiny fee early; never allocate more than remains.
    return min(remaining, money(total * Decimal(qty) / Decimal(total_qty)))


def replay_symbol(trades):
    """Replay one symbol's validated proposed history, returning (open, realized).

    Open lot dicts contain entry (Trade), symbol, remaining qty and fees. Realized
    dicts contain entry/exit (Trade), symbol, qty, buy_fees, sell_fees, pnl (after
    fees, rounded to money), and holding_days. Inputs are never mutated. An
    oversized sell or ambiguous same-symbol ordering raises ValueError.
    """
    trades = order_trades(trades)
    if len({trade.symbol for trade in trades}) > 1:
        raise ValueError("Replay requires one symbol.")
    if len({(trade.date, trade.seq) for trade in trades}) != len(trades):
        raise ValueError("Each trade needs a unique date and sequence per symbol.")
    lots = deque()
    realized = []
    available = 0
    for trade in trades:
        if trade.side == "buy":
            lots.append(
                {"entry": trade, "symbol": trade.symbol, "qty": trade.qty, "fees": trade.fees}
            )
            available += trade.qty
            continue
        if trade.qty > available:
            raise ValueError(f"Sell exceeds open quantity for {trade.symbol}.")
        remaining_qty = trade.qty
        remaining_fees = trade.fees
        while remaining_qty:
            lot = lots[0]
            entry = lot["entry"]
            qty = min(remaining_qty, lot["qty"])
            buy_fees = _fee_portion(entry.fees, qty, entry.qty, lot["fees"], qty == lot["qty"])
            sell_fees = _fee_portion(
                trade.fees, qty, trade.qty, remaining_fees, qty == remaining_qty
            )
            realized.append(
                {
                    "entry": entry,
                    "exit": trade,
                    "symbol": trade.symbol,
                    "qty": qty,
                    "buy_fees": buy_fees,
                    "sell_fees": sell_fees,
                    "pnl": money((trade.price - entry.price) * Decimal(qty) - buy_fees - sell_fees),
                    "holding_days": (trade.date - entry.date).days,
                }
            )
            lot["qty"] -= qty
            lot["fees"] -= buy_fees
            remaining_qty -= qty
            remaining_fees -= sell_fees
            if not lot["qty"]:
                lots.popleft()
        available -= trade.qty
    return list(lots), realized
