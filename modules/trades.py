"""Trade repository: persistence, version claims, and FIFO replay validation."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pymongo
from bson.objectid import ObjectId

import modules.portfolios as portfolios
import modules.prices as prices
from modules.ledger import Trade, replay_symbol, validate_trade
from modules.pnl import fifo_positions, summary
from sources.functions import utcnow
from sources.money import from_d128, money, price, to_d128


def ensure_indexes(db):
    """Ensure indexes on trades collection."""
    db.trades.create_index(
        [
            ("portfolio_id", pymongo.ASCENDING),
            ("symbol", pymongo.ASCENDING),
            ("date", pymongo.ASCENDING),
            ("seq", pymongo.ASCENDING),
        ]
    )


def _normalize_date(val):
    """Normalize date, datetime, or ISO string to UTC midnight datetime."""
    if isinstance(val, datetime):
        return datetime(val.year, val.month, val.day, 0, 0, 0, tzinfo=timezone.utc)
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day, 0, 0, 0, tzinfo=timezone.utc)
    if isinstance(val, str):
        parsed = date.fromisoformat(val.strip())
        return datetime(parsed.year, parsed.month, parsed.day, 0, 0, 0, tzinfo=timezone.utc)
    raise TypeError(f"Expected date, datetime or ISO string, got {type(val).__name__}")


def _doc_to_trade(doc):
    """Convert MongoDB trade document to Trade dataclass."""
    d = doc["date"]
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return Trade(
        portfolio_id=doc["portfolio_id"],
        symbol=doc["symbol"],
        side=doc["side"],
        qty=int(doc["qty"]),
        price=from_d128(doc["price"]),
        fees=from_d128(doc["fees"]),
        date=d,
        seq=int(doc.get("seq", 0)),
        source=doc.get("source", "manual"),
        import_id=doc.get("import_id"),
    )


def _trade_to_doc(trade):
    """Convert Trade dataclass to MongoDB document dict with Decimal128."""
    return {
        "portfolio_id": portfolios._to_object_id(trade.portfolio_id),
        "symbol": trade.symbol,
        "side": trade.side,
        "qty": trade.qty,
        "price": to_d128(trade.price),
        "fees": to_d128(trade.fees),
        "date": trade.date,
        "seq": trade.seq,
        "source": trade.source,
        "import_id": trade.import_id,
    }


def get_trade(db, trade_id, portfolio_id=None):
    """Retrieve a trade by ID, optionally verifying portfolio_id."""
    if not isinstance(trade_id, ObjectId) and not (
        isinstance(trade_id, str) and ObjectId.is_valid(trade_id)
    ):
        return None

    query = {"_id": portfolios._to_object_id(trade_id)}
    if portfolio_id is not None:
        query["portfolio_id"] = portfolios._to_object_id(portfolio_id)

    return db.trades.find_one(query)


def list_trades(db, portfolio_id):
    """List all trades for a portfolio ordered by (date, seq)."""
    portfolio_oid = portfolios._to_object_id(portfolio_id)
    return list(db.trades.find({"portfolio_id": portfolio_oid}).sort([("date", 1), ("seq", 1)]))


def add_trade(
    db,
    user_id,
    portfolio_id,
    symbol,
    side,
    qty,
    price_val,
    fees_val,
    trade_date,
    expected_version,
    source="manual",
    import_id=None,
):
    """Add a trade with optimistic portfolio claim and historical replay validation."""
    portfolio = portfolios.claim_portfolio(db, portfolio_id, user_id, expected_version)

    clean_symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
    clean_side = side.strip().lower() if isinstance(side, str) else ""
    int_qty = int(qty)
    price_dec = price(price_val)
    fees_dec = money(fees_val)
    d_utc = _normalize_date(trade_date)

    existing_same_day = list(
        db.trades.find({
            "portfolio_id": portfolio["_id"],
            "symbol": clean_symbol,
            "date": d_utc,
        })
    )
    next_seq = max([t.get("seq", 0) for t in existing_same_day], default=-1) + 1

    trade = Trade(
        portfolio_id=portfolio["_id"],
        symbol=clean_symbol,
        side=clean_side,
        qty=int_qty,
        price=price_dec,
        fees=fees_dec,
        date=d_utc,
        seq=next_seq,
        source=source,
        import_id=import_id,
    )
    validate_trade(trade, portfolio["currency"])

    existing_docs = list(
        db.trades.find({
            "portfolio_id": portfolio["_id"],
            "symbol": clean_symbol,
        })
    )
    existing_trades = [_doc_to_trade(doc) for doc in existing_docs]
    proposed_trades = existing_trades + [trade]
    replay_symbol(proposed_trades)

    doc = _trade_to_doc(trade)
    doc["created_at"] = utcnow()
    return db.trades.insert_one(doc).inserted_id


def edit_trade(
    db,
    user_id,
    portfolio_id,
    trade_id,
    symbol,
    side,
    qty,
    price_val,
    fees_val,
    trade_date,
    expected_version,
    seq=None,
):
    """Edit an existing trade with historical replay validation across affected symbols."""
    portfolio_oid = portfolios._to_object_id(portfolio_id)
    trade_oid = portfolios._to_object_id(trade_id)

    existing_trade_doc = db.trades.find_one({"_id": trade_oid, "portfolio_id": portfolio_oid})
    if not existing_trade_doc:
        raise ValueError("Trade not found.")

    portfolio = portfolios.claim_portfolio(db, portfolio_id, user_id, expected_version)

    clean_symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
    clean_side = side.strip().lower() if isinstance(side, str) else ""
    int_qty = int(qty)
    price_dec = price(price_val)
    fees_dec = money(fees_val)
    d_utc = _normalize_date(trade_date)
    orig_symbol = existing_trade_doc["symbol"]
    orig_date = _normalize_date(existing_trade_doc["date"])

    if seq is None:
        if d_utc == orig_date and clean_symbol == orig_symbol:
            assigned_seq = existing_trade_doc.get("seq", 0)
        else:
            existing_same_day = list(
                db.trades.find({
                    "portfolio_id": portfolio["_id"],
                    "symbol": clean_symbol,
                    "date": d_utc,
                    "_id": {"$ne": trade_oid},
                })
            )
            assigned_seq = max([t.get("seq", 0) for t in existing_same_day], default=-1) + 1
    else:
        assigned_seq = int(seq)

    updated_trade = Trade(
        portfolio_id=portfolio["_id"],
        symbol=clean_symbol,
        side=clean_side,
        qty=int_qty,
        price=price_dec,
        fees=fees_dec,
        date=d_utc,
        seq=assigned_seq,
        source=existing_trade_doc.get("source", "manual"),
        import_id=existing_trade_doc.get("import_id"),
    )
    validate_trade(updated_trade, portfolio["currency"])

    if clean_symbol == orig_symbol:
        existing_docs = list(
            db.trades.find({"portfolio_id": portfolio["_id"], "symbol": orig_symbol})
        )
        proposed = []
        for d in existing_docs:
            if d["_id"] == trade_oid:
                proposed.append(updated_trade)
            else:
                proposed.append(_doc_to_trade(d))
        replay_symbol(proposed)
    else:
        orig_docs = list(
            db.trades.find({
                "portfolio_id": portfolio["_id"],
                "symbol": orig_symbol,
                "_id": {"$ne": trade_oid},
            })
        )
        orig_remaining = [_doc_to_trade(d) for d in orig_docs]
        if orig_remaining:
            replay_symbol(orig_remaining)

        new_docs = list(db.trades.find({"portfolio_id": portfolio["_id"], "symbol": clean_symbol}))
        new_proposed = [_doc_to_trade(d) for d in new_docs] + [updated_trade]
        replay_symbol(new_proposed)

    update_doc = _trade_to_doc(updated_trade)
    update_doc["updated_at"] = utcnow()
    db.trades.update_one({"_id": trade_oid}, {"$set": update_doc})
    return True


def delete_trade(db, user_id, portfolio_id, trade_id, expected_version):
    """Delete a trade after historical replay validation proves no subsequent sell is orphaned."""
    portfolio_oid = portfolios._to_object_id(portfolio_id)
    trade_oid = portfolios._to_object_id(trade_id)

    existing_trade_doc = db.trades.find_one({"_id": trade_oid, "portfolio_id": portfolio_oid})
    if not existing_trade_doc:
        raise ValueError("Trade not found.")

    portfolio = portfolios.claim_portfolio(db, portfolio_id, user_id, expected_version)

    symbol = existing_trade_doc["symbol"]
    remaining_docs = list(
        db.trades.find({
            "portfolio_id": portfolio["_id"],
            "symbol": symbol,
            "_id": {"$ne": trade_oid},
        })
    )
    remaining_trades = [_doc_to_trade(d) for d in remaining_docs]
    if remaining_trades:
        replay_symbol(remaining_trades)

    db.trades.delete_one({"_id": trade_oid})
    return True


def get_portfolio_dashboard_data(db, portfolio):
    """Compile open positions, realized lot portions, and summary statistics."""
    raw_trades = list_trades(db, portfolio["_id"])
    trade_objs = [_doc_to_trade(d) for d in raw_trades]
    open_lots, realized = fifo_positions(trade_objs)
    stats = summary(realized)

    symbol_lots_map = {}
    for lot in open_lots:
        symbol_lots_map.setdefault(lot["symbol"], []).append(lot)

    open_positions = []
    unrealized_sum = Decimal("0.00")
    priced_count = 0
    latest_market_date = None

    for sym, lots in symbol_lots_map.items():
        shares = sum(lot["qty"] for lot in lots)
        total_cost = sum(lot["entry"].price * Decimal(lot["qty"]) + lot["fees"] for lot in lots)
        cost_per_share = price(total_cost / Decimal(shares))

        bar = prices.latest_bar(db, sym)
        if bar:
            last_close = price(bar["close"])
            p_date = bar["date"].strftime("%d %b %Y")
            if latest_market_date is None or bar["date"] > latest_market_date:
                latest_market_date = bar["date"]
            unrealized = money((last_close * Decimal(shares)) - total_cost)
            unrealized_sum += unrealized
            priced_count += 1
            open_positions.append({
                "symbol": sym,
                "shares": shares,
                "cost_per_share": cost_per_share,
                "last_close": last_close,
                "price_date": p_date,
                "unrealized": unrealized,
                "is_pos": unrealized > 0,
                "is_neg": unrealized < 0,
                "has_price": True,
            })
        else:
            open_positions.append({
                "symbol": sym,
                "shares": shares,
                "cost_per_share": cost_per_share,
                "last_close": None,
                "price_date": None,
                "unrealized": None,
                "is_pos": False,
                "is_neg": False,
                "has_price": False,
            })

    if not open_positions:
        unrealized_total = Decimal("0.00")
        has_price_error = False
    elif priced_count == 0:
        unrealized_total = None
        has_price_error = True
    else:
        unrealized_total = money(unrealized_sum)
        has_price_error = priced_count < len(open_positions)

    realized_items = []
    for r in realized:
        realized_items.append({
            "symbol": r["symbol"],
            "closed_date": r["exit"].date.strftime("%d %b %Y"),
            "shares": r["qty"],
            "entry_price": price(r["entry"].price),
            "exit_price": price(r["exit"].price),
            "pnl": r["pnl"],
            "is_pos": r["pnl"] > 0,
            "is_neg": r["pnl"] < 0,
            "holding_days": r["holding_days"],
        })

    trades_display = []
    for d in reversed(raw_trades):
        d_tz = d["date"] if d["date"].tzinfo else d["date"].replace(tzinfo=timezone.utc)
        trades_display.append({
            "_id": str(d["_id"]),
            "symbol": d["symbol"],
            "side": d["side"],
            "qty": d["qty"],
            "price": price(from_d128(d["price"])),
            "fees": money(from_d128(d["fees"])),
            "date_str": d_tz.strftime("%Y-%m-%d"),
            "display_date": d_tz.strftime("%d %b %Y"),
            "seq": d.get("seq", 0),
            "source": d.get("source", "manual"),
        })

    as_of_date = (
        latest_market_date.strftime("%d %b %Y")
        if latest_market_date
        else utcnow().strftime("%d %b %Y")
    )

    wins_count = sum(1 for r in realized if r["pnl"] > 0)
    total_portions = len(realized)

    return {
        "portfolio": portfolio,
        "as_of_date": as_of_date,
        "open_positions": open_positions,
        "realized_items": realized_items,
        "stats": stats,
        "unrealized_total": unrealized_total,
        "has_price_error": has_price_error,
        "wins_count": wins_count,
        "total_portions": total_portions,
        "trades_display": trades_display,
    }
