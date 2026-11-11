"""Server-side import previews and guarded confirmation with rollback."""

from dataclasses import replace
from datetime import timedelta

from bson.objectid import ObjectId
from pymongo.errors import PyMongoError

from modules import portfolios, trades
from modules.ledger import Trade, validate_trade
from modules.pnl import fifo_positions
from sources.functions import utcnow


class PreviewNotFoundError(Exception):
    """A preview is missing, expired, or owned by someone else."""


def ensure_indexes(db):
    db.import_previews.create_index("created_at", expireAfterSeconds=3600)


def create_preview(db, user_id, portfolio_id, rows, source, *, requires_acknowledgement=False):
    """Store validated rows in Mongo, returning only the new preview ID."""
    portfolio = portfolios.get_portfolio(db, portfolio_id, user_id=user_id)
    if not portfolio:
        raise portfolios.PortfolioNotFoundError("Portfolio not found.")
    if source not in ("csv", "pdf"):
        raise ValueError("Import source must be csv or pdf.")
    if source == "pdf" and portfolio["currency"] != "MYR":
        raise ValueError("Synthetic contract notes require a MYR portfolio.")
    if not rows:
        raise ValueError("No trades to import.")
    documents = []
    for seq, row in enumerate(rows):
        trade = Trade(
            portfolio_id=portfolio["_id"], symbol=row["symbol"], side=row["side"],
            qty=row["qty"], price=row["price"], fees=row["fees"],
            date=row["date"], seq=seq, source=source,
        )
        validate_trade(trade, portfolio["currency"])
        documents.append(trades._trade_to_doc(trade))
    return db.import_previews.insert_one({
        "user_id": portfolio["user_id"], "portfolio_id": portfolio["_id"],
        "rows": documents, "source": source, "status": "pending", "created_at": utcnow(),
        "requires_acknowledgement": requires_acknowledgement,
    }).inserted_id


def confirm_preview(db, user_id, preview_id, *, acknowledge_mismatch=False):
    """Claim a pending preview once, replay current history, then insert its rows.

    Repeated confirms return the existing status without inserting again. Failed
    previews require a fresh upload. Rollback targets only this import's rows.
    """
    if not isinstance(preview_id, (str, ObjectId)) or not ObjectId.is_valid(preview_id):
        raise PreviewNotFoundError("Preview not found.")
    query = {
        "_id": ObjectId(preview_id), "user_id": portfolios._to_object_id(user_id),
        "created_at": {"$gt": utcnow() - timedelta(hours=1)},
    }
    preview = db.import_previews.find_one(query)
    if not preview:
        raise PreviewNotFoundError("Preview not found.")
    portfolio = portfolios.get_portfolio(db, preview["portfolio_id"], user_id=user_id)
    if not portfolio:
        raise portfolios.PortfolioNotFoundError("Portfolio not found.")
    if preview.get("source") == "pdf" and portfolio["currency"] != "MYR":
        raise ValueError("Synthetic contract notes require a MYR portfolio.")
    claim_fields = {"status": "confirming"}
    if preview["status"] == "pending" and preview.get("requires_acknowledgement"):
        if not acknowledge_mismatch:
            raise ValueError(
                "Acknowledge the contract note reconciliation mismatch before confirming."
            )
        claim_fields["mismatch_acknowledged"] = True
    result = db.import_previews.update_one(
        {**query, "status": "pending"}, {"$set": claim_fields},
    )
    if not result.modified_count:
        return db.import_previews.find_one({"_id": preview["_id"]})

    import_id = preview["_id"]
    try:
        portfolio = portfolios.claim_portfolio(
            db, portfolio["_id"], user_id, portfolio["version"],
        )
        existing = [trades._doc_to_trade(doc) for doc in trades.list_trades(db, portfolio["_id"])]
        next_sequences = {}
        for trade in existing:
            key = (trade.symbol, trade.date)
            next_sequences[key] = max(next_sequences.get(key, 0), trade.seq + 1)
        proposed = []
        for row in preview["rows"]:
            trade = trades._doc_to_trade(row)
            key = (trade.symbol, trade.date)
            seq = next_sequences.get(key, 0)
            trade = replace(trade, seq=seq, import_id=import_id)
            validate_trade(trade, portfolio["currency"])
            proposed.append(trade)
            next_sequences[key] = seq + 1
        fifo_positions(existing + proposed)
        documents = [trades._trade_to_doc(trade) for trade in proposed]
        db.trades.insert_many(documents)
        db.import_previews.update_one(
            {"_id": import_id}, {"$set": {"status": "confirmed"}},
        )
    except (
        ValueError, TypeError, PyMongoError, portfolios.StaleVersionError,
        portfolios.PortfolioNotFoundError,
    ):
        db.trades.delete_many({"portfolio_id": portfolio["_id"], "import_id": import_id})
        db.import_previews.update_one({"_id": import_id}, {"$set": {"status": "failed"}})
        raise
    return {**preview, "status": "confirmed"}
