from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from modules.ledger import Trade, group_by_symbol, order_trades, replay_symbol, validate_trade


def sample_trade(**changes):
    return replace(
        Trade(
            "portfolio",
            "DEMO1",
            "buy",
            10,
            Decimal("1.2345"),
            Decimal("2.88"),
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            0,
        ),
        **changes,
    )


def test_trade_is_frozen_and_validation_does_not_change_actual_fees():
    trade = sample_trade(fees=Decimal("7.77"), source="csv", import_id="import")
    assert validate_trade(trade, "MYR") is trade
    with pytest.raises(FrozenInstanceError):
        trade.qty = 2


@pytest.mark.parametrize(
    "symbol,currency",
    [("1155.KL", "MYR"), ("AAPL", "USD"), ("CUSTOM-X", "MYR"), ("CUSTOM-X", "USD")],
)
def test_known_and_free_text_symbol_currencies(symbol, currency):
    assert validate_trade(sample_trade(symbol=symbol), currency).symbol == symbol


@pytest.mark.parametrize("symbol,currency", [("AAPL", "MYR"), ("DEMO1", "USD"), ("1155.KL", "USD")])
def test_currency_mismatch_rejected(symbol, currency):
    with pytest.raises(ValueError, match="currency"):
        validate_trade(sample_trade(symbol=symbol), currency)


@pytest.mark.parametrize(
    "changes",
    [
        {"portfolio_id": None},
        {"symbol": "demo1"},
        {"symbol": " DEMO1"},
        {"symbol": ""},
        {"symbol": "A\nB"},
        {"symbol": "X" * 33},
        {"side": "short"},
        {"qty": 0},
        {"qty": -1},
        {"qty": True},
        {"qty": Decimal("1")},
        {"qty": 1.5},
        {"price": Decimal("0")},
        {"price": Decimal("-1")},
        {"price": 1.2},
        {"price": Decimal("NaN")},
        {"price": Decimal("Infinity")},
        {"price": Decimal("1.00001")},
        {"fees": Decimal("-0.01")},
        {"fees": "2.88"},
        {"fees": Decimal("NaN")},
        {"fees": Decimal("Infinity")},
        {"fees": Decimal("0.001")},
        {"seq": -1},
        {"seq": True},
        {"seq": "1"},
        {"source": "unknown"},
        {"date": date(2026, 1, 1)},
        {"date": datetime(2026, 1, 1)},
        {"date": datetime(2026, 1, 1, 1, tzinfo=timezone.utc)},
        {"date": datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=8)))},
    ],
)
def test_invalid_trade_boundary(changes):
    with pytest.raises(ValueError):
        validate_trade(sample_trade(**changes), "MYR")


def test_invalid_portfolio_currency_or_record():
    with pytest.raises(ValueError):
        validate_trade(sample_trade(), "EUR")
    with pytest.raises(ValueError):
        validate_trade({}, "MYR")


def test_ordering_and_grouping_are_by_date_then_seq_and_do_not_mutate():
    first = sample_trade(seq=1)
    later_seq = sample_trade(seq=2)
    later_date = sample_trade(date=datetime(2026, 1, 2, tzinfo=timezone.utc))
    other = sample_trade(symbol="DEMO2")
    rows = [later_date, later_seq, other, first]
    assert order_trades([later_date, later_seq, first]) == [first, later_seq, later_date]
    assert group_by_symbol(iter(rows)) == {
        "DEMO1": [first, later_seq, later_date],
        "DEMO2": [other],
    }
    assert rows == [later_date, later_seq, other, first]


@pytest.mark.parametrize("mutation", ["edit", "delete", "backdate"])
def test_full_history_replay_rejects_invalid_historical_change(mutation):
    buy = sample_trade(qty=10)
    sell = sample_trade(side="sell", qty=8, seq=1)
    future_buy = sample_trade(qty=100, date=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert replay_symbol([buy, sell, future_buy])[1][0]["qty"] == 8
    if mutation == "edit":
        proposed = [replace(buy, qty=7), sell, future_buy]
    elif mutation == "delete":
        proposed = [sell, future_buy]
    else:
        proposed = [buy, replace(sell, date=buy.date - timedelta(days=1)), future_buy]
    with pytest.raises(ValueError, match="exceeds open quantity"):
        replay_symbol(proposed)
    assert buy.qty == 10


def test_replay_rejects_mixed_symbols_and_ambiguous_sequences():
    with pytest.raises(ValueError, match="one symbol"):
        replay_symbol([sample_trade(), sample_trade(symbol="DEMO2")])
    with pytest.raises(ValueError, match="unique"):
        replay_symbol([sample_trade(), sample_trade(side="sell")])
