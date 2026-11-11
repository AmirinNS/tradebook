"""Pure, deterministic 30-day market game. Inputs are never mutated.

State is a plain dict with seed (int), day (1..30), cash/principal/interest
(2-place Decimal), holdings ({symbol: positive int}), prices ({symbol: list
of 30 4-place Decimal closes}), news (30 dicts with day/sector/headline),
and score (None until day 30, then a 2-place Decimal). G2 must recursively
convert Decimals through sources.money.to_d128/from_d128 for BSON storage.

Actions are dicts: {type: buy|sell, symbol: str, qty: int}, {type: repay,
amount: Decimal|str|int}, or {type: next_day}. apply_action returns a new
state. Repayments require exact sen and pay interest before principal.
Interest is rounded daily on principal only, with 29 accruals in a game.
Arrival at day 30 finishes the game immediately; no later action is valid.

public_view returns JSON-ready decimal strings and independent containers.
It includes only today's market, history/news through today, balances,
holdings, net worth and completion information, never seed or future data.
"""

import random
from copy import deepcopy
from decimal import Decimal, InvalidOperation

from sources.money import as_decimal, money, price, to_json

DAYS = 30
INTEREST_RATE = Decimal("0.005")
DAILY_DRIFT = Decimal("0.0005")
DAILY_VOLATILITY = Decimal("0.025")
COMPANIES = (
    ("VEL", "Velunex Circuits", "Technology", "12"),
    ("ORV", "Orvessa Harvest", "Agriculture", "8"),
    ("PEL", "Pelmora Power", "Energy", "18"),
    ("NAL", "Naluvia Clinics", "Healthcare", "24"),
    ("TAV", "Tavrilo Freight", "Transport", "15"),
    ("ZEP", "Zephuni Markets", "Retail", "10"),
)


class GameError(ValueError):
    """An invalid game action or seed."""


def _daily_news(seed, day):
    generator = random.Random(seed * 1000 + day)
    sector = generator.choice(COMPANIES)[2]
    shock = generator.choice((Decimal("-0.06"), Decimal("-0.03"), Decimal("0.03"), Decimal("0.06")))
    headline = f"{sector} demand {'improves' if shock > 0 else 'weakens'}."
    return {"day": day, "sector": sector, "headline": headline}, shock


def new_game(seed):
    """Start with RM20,000 cash, RM10,000 principal, no unpaid interest."""
    if type(seed) is not int:
        raise GameError("Seed must be an integer.")
    generator = random.Random(seed)
    paths = {symbol: [] for symbol, _, _, _ in COMPANIES}
    news = []
    for day in range(1, DAYS + 1):
        event, shock = _daily_news(seed, day)
        news.append(event)
        for symbol, _, sector, initial_price in COMPANIES:
            previous = paths[symbol][-1] if day > 1 else price(initial_price)
            factor = Decimal(1)
            if day > 1:
                normal = Decimal(str(generator.gauss(0, 1)))
                factor = (DAILY_DRIFT - DAILY_VOLATILITY**2 / 2 + DAILY_VOLATILITY * normal).exp()
            if sector == event["sector"]:
                factor *= Decimal(1) + shock
            paths[symbol].append(max(Decimal("0.0001"), price(previous * factor)))
    return {
        "seed": seed,
        "day": 1,
        "cash": money("20000"),
        "principal": money("10000"),
        "interest": money("0"),
        "holdings": {},
        "prices": paths,
        "news": news,
        "score": None,
    }


def _net_worth(state):
    holdings_value = sum(
        (
            state["prices"][symbol][state["day"] - 1] * Decimal(qty)
            for symbol, qty in state["holdings"].items()
        ),
        Decimal(0),
    )
    return money(state["cash"] + holdings_value - state["principal"] - state["interest"])


def apply_action(state, action):
    """Validate an action, returning a new state or raising GameError."""
    if state["day"] >= DAYS:
        raise GameError("The game has finished.")
    if not isinstance(action, dict) or action.get("type") not in (
        "buy",
        "sell",
        "repay",
        "next_day",
    ):
        raise GameError("Choose buy, sell, repay or next_day.")
    result = deepcopy(state)
    action_type = action["type"]
    if action_type in ("buy", "sell"):
        symbol = action.get("symbol")
        if not isinstance(symbol, str) or symbol not in state["prices"]:
            raise GameError("Choose a company from the market.")
        qty = action.get("qty")
        if type(qty) is not int or qty <= 0:
            raise GameError("Quantity must be a positive integer.")
        try:
            total = money(state["prices"][symbol][state["day"] - 1] * Decimal(qty))
        except InvalidOperation:
            raise GameError("Quantity is too large.") from None
        held = state["holdings"].get(symbol, 0)
        if action_type == "buy":
            if total > state["cash"]:
                raise GameError("Not enough cash to buy these shares.")
            result["cash"] -= total
            result["holdings"][symbol] = held + qty
        else:
            if qty > held:
                raise GameError("You cannot sell more shares than you hold.")
            result["cash"] += total
            if qty == held:
                result["holdings"].pop(symbol)
            else:
                result["holdings"][symbol] = held - qty
    elif action_type == "repay":
        try:
            amount = action.get("amount")
            if isinstance(amount, bool):
                raise ValueError("Boolean amounts are invalid.")
            amount = as_decimal(amount)
            if amount <= 0 or amount > min(state["cash"], state["principal"] + state["interest"]):
                raise ValueError("Repayment is outside the available bounds.")
            if amount != money(amount):
                raise ValueError("Repayment must be in exact sen.")
        except (TypeError, ValueError, InvalidOperation):
            raise GameError(
                "Repay a positive amount in sen, at most your cash or total debt."
            ) from None
        amount = money(amount)
        interest_paid = min(amount, state["interest"])
        result["interest"] -= interest_paid
        result["principal"] -= amount - interest_paid
        result["cash"] = money(state["cash"] - amount)
    else:
        result["day"] += 1
        result["interest"] += money(state["principal"] * INTEREST_RATE)
        if result["day"] == DAYS:
            result["score"] = _net_worth(result)
    return result


def public_view(state):
    """Return only public, visible information, ready for JSON encoding."""
    day = state["day"]
    return {
        "day": day,
        "total_days": DAYS,
        "finished": day == DAYS,
        "cash": to_json(state["cash"]),
        "principal": to_json(state["principal"]),
        "interest": to_json(state["interest"]),
        "debt": to_json(state["principal"] + state["interest"]),
        "net_worth": to_json(_net_worth(state)),
        "score": to_json(state["score"]) if state["score"] is not None else None,
        "holdings": dict(state["holdings"]),
        "companies": [
            {
                "symbol": symbol,
                "name": name,
                "sector": sector,
                "price": to_json(state["prices"][symbol][day - 1]),
            }
            for symbol, name, sector, _ in COMPANIES
        ],
        "history": {
            symbol: [to_json(value) for value in values[:day]]
            for symbol, values in state["prices"].items()
        },
        "news": deepcopy(state["news"][:day]),
    }
