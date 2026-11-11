"""Pure engine checks, independent of Flask and MongoDB fixtures."""

import json
import random
from copy import deepcopy
from decimal import Decimal

import pytest
from bson import BSON

from modules import game_engine
from modules.game_engine import GameError, apply_action, new_game, public_view
from sources.money import from_d128, to_d128, to_json


def finish(state):
    while state["day"] < 30:
        state = apply_action(state, {"type": "next_day"})
    return state


def test_same_seed_same_game_without_global_random_side_effects():
    before = random.getstate()
    first = new_game(41)
    assert first == new_game(41)
    assert first["prices"] != new_game(42)["prices"]
    assert random.getstate() == before
    assert len(first["prices"]) == 6
    assert len({company[2] for company in game_engine.COMPANIES}) == 6
    for values in first["prices"].values():
        assert len(values) == 30
        assert all(isinstance(value, Decimal) and value > 0 for value in values)
        assert all(value.as_tuple().exponent == -4 for value in values)
    assert first["day"] == 1
    assert first["cash"] == Decimal("20000.00")
    assert first["principal"] == Decimal("10000.00")
    assert first["interest"] == Decimal("0.00")
    assert first["holdings"] == {}
    assert first["score"] is None
    assert public_view(first)["net_worth"] == "10000.00"


@pytest.mark.parametrize("seed", [None, True, "41", 1.5])
def test_seed_must_be_an_integer(seed):
    with pytest.raises(GameError):
        new_game(seed)


def test_news_is_seeded_by_day_and_shocks_only_its_sector(monkeypatch):
    monkeypatch.setattr(game_engine, "DAILY_DRIFT", Decimal(0))
    monkeypatch.setattr(game_engine, "DAILY_VOLATILITY", Decimal(0))
    state = new_game(41)
    for day, event in enumerate(state["news"], start=1):
        assert event["day"] == day
        expected_sector = random.Random(41000 + day).choice(game_engine.COMPANIES)[2]
        assert event["sector"] == expected_sector
        changed = []
        for symbol, _, sector, initial_price in game_engine.COMPANIES:
            previous = state["prices"][symbol][day - 2] if day > 1 else Decimal(initial_price)
            current = state["prices"][symbol][day - 1]
            if current != previous:
                changed.append(sector)
                ratio = current / previous
                assert abs(ratio - 1) == pytest.approx(Decimal("0.03"), abs=Decimal("0.0001")) or (
                    abs(ratio - 1) == pytest.approx(Decimal("0.06"), abs=Decimal("0.0001"))
                )
                assert (current > previous) == ("improves" in event["headline"])
        assert changed == [expected_sector]


def test_actions_return_independent_states_and_trades_use_current_close():
    original = new_game(41)
    snapshot = deepcopy(original)
    bought = apply_action(original, {"type": "buy", "symbol": "VEL", "qty": 7})
    assert original == snapshot
    assert bought["holdings"] == {"VEL": 7}
    assert original["prices"]["VEL"][0] == Decimal("11.6400")
    assert bought["cash"] == Decimal("19918.52")
    partial = apply_action(bought, {"type": "sell", "symbol": "VEL", "qty": 2})
    assert partial["cash"] == Decimal("19941.80")
    assert partial["holdings"] == {"VEL": 5}
    later = apply_action(partial, {"type": "next_day"})
    sold = apply_action(later, {"type": "sell", "symbol": "VEL", "qty": 5})
    proceeds = (later["prices"]["VEL"][1] * 5).quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")
    assert sold["cash"] == later["cash"] + proceeds
    assert sold["holdings"] == {}
    bought["prices"]["VEL"][0] = Decimal("99")
    bought["news"][0]["headline"] = "Changed"
    assert original == snapshot


def test_buy_exact_cash_and_reject_excess_without_mutation():
    state = new_game(41)
    state["cash"] = Decimal("23.28")
    assert apply_action(state, {"type": "buy", "symbol": "VEL", "qty": 2})["cash"] == 0
    snapshot = deepcopy(state)
    with pytest.raises(GameError, match="Not enough cash"):
        apply_action(state, {"type": "buy", "symbol": "VEL", "qty": 3})
    assert state == snapshot


@pytest.mark.parametrize("action_type", ["buy", "sell"])
def test_oversized_quantity_is_a_game_error(action_type):
    with pytest.raises(GameError):
        apply_action(new_game(41), {"type": action_type, "symbol": "VEL", "qty": 10**100})


def test_cannot_sell_unheld_or_more_than_held():
    state = new_game(41)
    with pytest.raises(GameError, match="more shares"):
        apply_action(state, {"type": "sell", "symbol": "VEL", "qty": 1})
    state = apply_action(state, {"type": "buy", "symbol": "VEL", "qty": 2})
    with pytest.raises(GameError, match="more shares"):
        apply_action(state, {"type": "sell", "symbol": "VEL", "qty": 3})
    assert state["holdings"] == {"VEL": 2}


@pytest.mark.parametrize("action_type", ["buy", "sell"])
@pytest.mark.parametrize("qty", [None, 0, -1, True, False, 1.0, "1", Decimal("1"), [], {}])
def test_trade_quantity_must_be_a_positive_integer(action_type, qty):
    with pytest.raises(GameError, match="positive integer"):
        apply_action(new_game(41), {"type": action_type, "symbol": "VEL", "qty": qty})


@pytest.mark.parametrize("action", [None, [], "buy", {}, {"type": "borrow"}, {"type": []}])
def test_invalid_action_is_a_game_error(action):
    with pytest.raises(GameError):
        apply_action(new_game(41), action)


@pytest.mark.parametrize("symbol", [None, [], {}, "UNKNOWN", "vel"])
def test_invalid_company_is_a_game_error(symbol):
    with pytest.raises(GameError):
        apply_action(new_game(41), {"type": "buy", "symbol": symbol, "qty": 1})


def test_interest_accrues_only_on_next_day_including_day_30():
    state = apply_action(new_game(41), {"type": "buy", "symbol": "VEL", "qty": 1})
    assert state["interest"] == Decimal("0.00")
    for day in range(2, 31):
        state = apply_action(state, {"type": "next_day"})
        assert state["day"] == day
        assert state["interest"] == Decimal(50) * (day - 1)
        assert state["principal"] == Decimal("10000.00")
    assert state["interest"] == Decimal("1450.00")
    assert state["score"] is not None


def test_zero_trade_score_reconciles_two_ways():
    final = finish(new_game(41))
    assert final["score"] == Decimal("8550.00")
    assert final["score"] == Decimal("10000.00") - 29 * Decimal("50.00")
    assert final["score"] == final["cash"] - final["principal"] - final["interest"]
    assert public_view(final)["score"] == "8550.00"


def test_final_score_marks_holdings_at_day_30_close():
    state = apply_action(new_game(41), {"type": "buy", "symbol": "VEL", "qty": 7})
    state = apply_action(state, {"type": "buy", "symbol": "ORV", "qty": 11})
    final = finish(state)
    expected = (
        final["cash"]
        + 7 * final["prices"]["VEL"][29]
        + 11 * final["prices"]["ORV"][29]
        - Decimal("11450.00")
    )
    expected = expected.quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")
    assert final["score"] == expected
    assert final["score"].as_tuple().exponent == -2
    assert public_view(final)["net_worth"] == str(expected)


@pytest.mark.parametrize(
    "action",
    [
        {"type": "next_day"},
        {"type": "buy", "symbol": "VEL", "qty": 1},
        {"type": "sell", "symbol": "VEL", "qty": 1},
        {"type": "repay", "amount": "1"},
    ],
)
def test_every_action_rejected_after_day_30(action):
    final = finish(new_game(41))
    snapshot = deepcopy(final)
    with pytest.raises(GameError, match="finished"):
        apply_action(final, action)
    assert final == snapshot


@pytest.mark.parametrize(
    "amount",
    [
        None,
        True,
        False,
        "",
        "abc",
        "NaN",
        "sNaN",
        "Infinity",
        "-Infinity",
        Decimal("NaN"),
        Decimal("Infinity"),
        0,
        -1,
        "10000.01",
        "0.001",
        1.5,
        [],
        {},
    ],
)
def test_repayment_bounds_and_invalid_amounts(amount):
    state = new_game(41)
    snapshot = deepcopy(state)
    with pytest.raises(GameError, match="Repay"):
        apply_action(state, {"type": "repay", "amount": amount})
    assert state == snapshot


def test_repayment_cannot_exceed_cash():
    state = new_game(41)
    state["cash"] = Decimal("1.00")
    with pytest.raises(GameError, match="Repay"):
        apply_action(state, {"type": "repay", "amount": "1.01"})
    assert apply_action(state, {"type": "repay", "amount": "1"})["cash"] == 0


@pytest.mark.parametrize("amount", [1, "1.0000", Decimal("1.0000"), "1e0"])
def test_repayment_keeps_two_place_balances(amount):
    state = apply_action(new_game(41), {"type": "repay", "amount": amount})
    assert state["principal"] == Decimal("9999.00")
    assert state["cash"] == Decimal("19999.00")
    for field in ("cash", "principal", "interest"):
        assert state[field].as_tuple().exponent == -2


def test_repayment_pays_interest_first_then_reduces_future_daily_interest():
    state = apply_action(new_game(41), {"type": "next_day"})
    paid_interest = apply_action(state, {"type": "repay", "amount": "25"})
    assert paid_interest["interest"] == Decimal("25.00")
    assert paid_interest["principal"] == Decimal("10000.00")
    repaid = apply_action(paid_interest, {"type": "repay", "amount": "1025"})
    assert repaid["interest"] == 0
    assert repaid["principal"] == Decimal("9000.00")
    assert repaid["cash"] == Decimal("18950.00")
    assert public_view(repaid)["net_worth"] == public_view(state)["net_worth"]
    assert apply_action(repaid, {"type": "next_day"})["interest"] == Decimal("45.00")


def test_daily_interest_rounds_half_up_and_full_repayment_stops_interest():
    state = apply_action(new_game(41), {"type": "repay", "amount": "9999"})
    assert apply_action(state, {"type": "next_day"})["interest"] == Decimal("0.01")
    state = apply_action(new_game(41), {"type": "next_day"})
    repaid = apply_action(state, {"type": "repay", "amount": "10050"})
    assert repaid["principal"] == repaid["interest"] == 0
    assert finish(repaid)["score"] == Decimal("9950.00")
    with pytest.raises(GameError):
        apply_action(repaid, {"type": "repay", "amount": "0.01"})


def test_public_view_is_json_ready_independent_and_never_contains_future_data():
    state = new_game(41)
    for day in range(1, 31):
        view = public_view(state)
        assert "seed" not in json.dumps(view)
        assert "prices" not in view
        assert set(view) == {
            "day",
            "total_days",
            "finished",
            "cash",
            "principal",
            "interest",
            "debt",
            "net_worth",
            "score",
            "holdings",
            "companies",
            "history",
            "news",
        }
        assert all(len(values) == day for values in view["history"].values())
        assert view["news"] == state["news"][:day]
        assert all(event["day"] <= day for event in view["news"])
        for company in view["companies"]:
            symbol = company["symbol"]
            assert company["price"] == str(state["prices"][symbol][day - 1])
            assert view["history"][symbol] == list(map(str, state["prices"][symbol][:day]))
        assert isinstance(view["cash"], str)
        assert view["finished"] == (day == 30)
        view["news"][0]["headline"] = "Changed"
        view["holdings"]["VEL"] = 999
        view["history"]["VEL"][0] = "999"
        assert state["news"][0]["headline"] != "Changed"
        assert state["holdings"] == {}
        if day < 30:
            state = apply_action(state, {"type": "next_day"})


def convert_decimals(value, convert):
    if isinstance(value, dict):
        return {key: convert_decimals(item, convert) for key, item in value.items()}
    if isinstance(value, list):
        return [convert_decimals(item, convert) for item in value]
    return convert(value)


def test_state_serializes_through_existing_money_helpers():
    state = finish(new_game(41))
    stored = convert_decimals(
        state, lambda item: to_d128(item) if isinstance(item, Decimal) else item
    )
    decoded = BSON.encode(stored).decode()
    restored = convert_decimals(
        decoded, lambda item: from_d128(item) if hasattr(item, "to_decimal") else item
    )
    assert restored == state
    rendered = convert_decimals(
        state, lambda item: to_json(item) if isinstance(item, Decimal) else item
    )
    assert json.loads(json.dumps(rendered)) == rendered
