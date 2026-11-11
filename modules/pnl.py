"""Pure FIFO positions and closed-lot statistics for one portfolio."""

from decimal import Decimal

from modules.ledger import group_by_symbol, replay_symbol
from sources.money import money


def fifo_positions(trades):
    """Return (open_lots, realized) for validated Trade records, grouped by symbol.

    Dictionary shapes are documented by ledger.replay_symbol. Symbols retain
    first-seen order; each symbol is replayed in (date, seq) order. No currency
    conversion is performed; callers validate against the portfolio first.
    """
    open_lots, realized = [], []
    for rows in group_by_symbol(trades).values():
        symbol_lots, symbol_realized = replay_symbol(rows)
        open_lots.extend(symbol_lots)
        realized.extend(symbol_realized)
    return open_lots, realized


def summary(realized):
    """Summarize closed portions. Win rate is a percentage of all portions.

    Break-even portions count in the denominator but are neither wins nor losses.
    Averages/largest values are zero for an empty category; losses are negative.
    Profit factor is gross wins / absolute gross losses, None with no losses.
    Win rate is None without closed portions. Monetary values use money rounding.
    """
    values = [portion["pnl"] for portion in realized]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    zero = Decimal("0.00")
    gross_wins, gross_losses = sum(wins, zero), sum(losses, zero)
    return {
        "total_pnl": money(sum(values, zero)),
        "win_rate": money(Decimal(len(wins)) * 100 / Decimal(len(values))) if values else None,
        "average_win": money(gross_wins / Decimal(len(wins))) if wins else zero,
        "average_loss": money(gross_losses / Decimal(len(losses))) if losses else zero,
        "profit_factor": gross_wins / abs(gross_losses) if losses else None,
        "largest_win": max(wins, default=zero),
        "largest_loss": min(losses, default=zero),
    }
