from datetime import datetime, timezone
from decimal import Decimal

import pytest

from modules.ledger import Trade
from modules.pnl import fifo_positions, summary


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


def test_empty_positions_and_summary():
    assert fifo_positions([]) == ([], [])
    assert summary([]) == {
        "total_pnl": Decimal("0.00"),
        "win_rate": None,
        "average_win": Decimal("0.00"),
        "average_loss": Decimal("0.00"),
        "profit_factor": None,
        "largest_win": Decimal("0.00"),
        "largest_loss": Decimal("0.00"),
    }


def test_same_day_seq_controls_fifo_even_when_input_is_reversed():
    early_buy = trade("buy", 3, price="10", fees="0.03", seq=1)
    late_buy = trade("buy", 2, price="20", fees="0.02", seq=2)
    sell = trade("sell", 4, price="30", fees="0.05", seq=3)
    lots, realized = fifo_positions([sell, late_buy, early_buy])
    assert lots == [{"entry": late_buy, "symbol": "DEMO1", "qty": 1, "fees": Decimal("0.01")}]
    assert [part["entry"] for part in realized] == [early_buy, late_buy]
    assert [part["exit"] for part in realized] == [sell, sell]
    assert [part["qty"] for part in realized] == [3, 1]
    assert [part["sell_fees"] for part in realized] == [Decimal("0.04"), Decimal("0.01")]
    assert [part["pnl"] for part in realized] == [Decimal("59.93"), Decimal("9.98")]
    assert [part["holding_days"] for part in realized] == [0, 0]


def test_interleaved_symbols_never_share_lots_and_holding_days_follow_dates():
    buy1 = trade("buy", 10, fees="1.00")
    buy2 = trade("buy", 5, price="20", day=2, symbol="DEMO2")
    sell1 = trade("sell", 4, price="12", fees="0.40", day=3)
    sell2 = trade("sell", 5, price="19", fees="0.50", day=4, symbol="DEMO2")
    rows = [buy1, buy2, sell1, sell2]
    lots, realized = fifo_positions(iter(rows))
    assert lots == [{"entry": buy1, "symbol": "DEMO1", "qty": 6, "fees": Decimal("0.60")}]
    assert [
        (part["symbol"], part["qty"], part["pnl"], part["holding_days"]) for part in realized
    ] == [("DEMO1", 4, Decimal("7.20"), 2), ("DEMO2", 5, Decimal("-5.50"), 2)]
    assert rows == [buy1, buy2, sell1, sell2]


def test_partial_closes_leave_buy_fee_remainder_on_last_allocation():
    buy = trade("buy", 3, fees="0.01")
    first = trade("sell", 1, price="11", day=2)
    second = trade("sell", 1, price="11", day=3)
    lots, realized = fifo_positions([buy, first, second])
    assert lots[0]["qty"] == 1
    assert lots[0]["fees"] == Decimal("0.01")
    assert sum(part["buy_fees"] for part in realized) == Decimal("0.00")
    final = trade("sell", 1, price="11", day=4)
    lots, realized = fifo_positions([buy, first, second, final])
    assert lots == []
    assert [part["buy_fees"] for part in realized] == [
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.01"),
    ]
    assert summary(realized)["total_pnl"] == Decimal("2.99")


@pytest.mark.parametrize("fee", ["0.00", "0.01", "0.02", "0.05", "2.88"])
@pytest.mark.parametrize("qty", [3, 4, 7])
def test_many_partial_closes_conserve_buy_fees_to_the_sen(fee, qty):
    buy = trade("buy", qty, fees=fee)
    sells = [trade("sell", 1, seq=i + 1) for i in range(qty)]
    for closed_count in range(1, qty + 1):
        lots, realized = fifo_positions([buy, *sells[:closed_count]])
        allocated = sum((part["buy_fees"] for part in realized), Decimal(0))
        remaining = sum((lot["fees"] for lot in lots), Decimal(0))
        assert allocated + remaining == Decimal(fee)
        assert all(part["buy_fees"] >= 0 for part in realized)
        assert all(lot["fees"] >= 0 for lot in lots)
    assert lots == []
    # Independently reconcile equal-price round trips to their actual costs.
    assert sum(part["pnl"] for part in realized) == -Decimal(fee)


def test_sell_fees_across_three_lots_put_rounding_remainder_on_last():
    buys = [trade("buy", 1, seq=i) for i in range(3)]
    _, realized = fifo_positions([*buys, trade("sell", 3, fees="0.01", seq=3)])
    assert [part["sell_fees"] for part in realized] == [
        Decimal("0.00"),
        Decimal("0.00"),
        Decimal("0.01"),
    ]
    assert sum(part["sell_fees"] for part in realized) == Decimal("0.01")


@pytest.mark.parametrize(
    "rows",
    [
        [trade("sell", 1)],
        [trade("buy", 2), trade("sell", 3, seq=1)],
        [trade("sell", 1), trade("buy", 2, seq=1)],
        [trade("buy", 10, symbol="DEMO2"), trade("sell", 1)],
    ],
)
def test_oversized_sells_fail_for_the_affected_symbol(rows):
    with pytest.raises(ValueError, match="exceeds open quantity"):
        fifo_positions(rows)


def test_summary_counts_closed_portions_and_break_even_is_neither_win_nor_loss():
    realized = [{"pnl": Decimal(value)} for value in ("10.00", "20.00", "-5.00", "0.00")]
    assert summary(realized) == {
        "total_pnl": Decimal("25.00"),
        "win_rate": Decimal("50.00"),
        "average_win": Decimal("15.00"),
        "average_loss": Decimal("-5.00"),
        "profit_factor": Decimal("6"),
        "largest_win": Decimal("20.00"),
        "largest_loss": Decimal("-5.00"),
    }
    assert summary([{"pnl": Decimal("0.00")}])["win_rate"] == Decimal("0.00")
    assert summary([{"pnl": Decimal("0.00")}])["profit_factor"] is None


def test_summary_with_no_losses_and_only_losses():
    assert summary([{"pnl": Decimal("1.00")}])["profit_factor"] is None
    stats = summary([{"pnl": Decimal("-1.00")}, {"pnl": Decimal("-2.00")}])
    assert stats["win_rate"] == Decimal("0.00")
    assert stats["average_loss"] == Decimal("-1.50")
    assert stats["largest_loss"] == Decimal("-2.00")
    assert stats["profit_factor"] == Decimal(0)


def test_four_place_price_pnl_rounds_half_up():
    _, realized = fifo_positions(
        [trade("buy", 1, price="1.0000"), trade("sell", 1, price="1.0050", seq=1)]
    )
    assert realized[0]["pnl"] == Decimal("0.01")
