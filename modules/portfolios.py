"""Portfolio repository: single-currency portfolios scoped by user with optimistic concurrency."""

from bson.objectid import ObjectId

from sources.functions import utcnow


class StaleVersionError(Exception):
    """Raised when a portfolio write conflicts with a newer version."""


class PortfolioNotFoundError(Exception):
    """Raised when a portfolio does not exist or belongs to another user."""


def ensure_indexes(db):
    """Ensure indexes on portfolios collection."""
    db.portfolios.create_index("user_id")


def _to_object_id(val):
    if isinstance(val, ObjectId):
        return val
    if isinstance(val, str) and ObjectId.is_valid(val):
        return ObjectId(val)
    return val


def create_portfolio(db, user_id, name, currency="MYR"):
    """Create a new portfolio document with initial version 1."""
    user_oid = _to_object_id(user_id)
    if not user_oid:
        raise ValueError("A valid user_id is required.")

    clean_name = name.strip() if isinstance(name, str) else ""
    if not clean_name or len(clean_name) > 100:
        raise ValueError("Portfolio name is required and must be at most 100 characters.")

    clean_currency = currency.strip().upper() if isinstance(currency, str) else ""
    if clean_currency not in ("MYR", "USD"):
        raise ValueError("Portfolio currency must be MYR or USD.")

    doc = {
        "user_id": user_oid,
        "name": clean_name,
        "currency": clean_currency,
        "version": 1,
        "created_at": utcnow(),
    }
    return db.portfolios.insert_one(doc).inserted_id


def get_portfolio(db, portfolio_id, user_id=None):
    """Retrieve a portfolio by ID, optionally verifying ownership."""
    if not isinstance(portfolio_id, ObjectId) and not (
        isinstance(portfolio_id, str) and ObjectId.is_valid(portfolio_id)
    ):
        return None

    query = {"_id": _to_object_id(portfolio_id)}
    if user_id is not None:
        query["user_id"] = _to_object_id(user_id)

    return db.portfolios.find_one(query)


def list_portfolios(db, user_id):
    """List all portfolios owned by user_id sorted by creation time."""
    user_oid = _to_object_id(user_id)
    return list(db.portfolios.find({"user_id": user_oid}).sort("created_at", 1))


def claim_portfolio(db, portfolio_id, user_id, expected_version):
    """Optimistically claim the portfolio by incrementing its version.

    Returns the updated portfolio document.
    Raises PortfolioNotFoundError if not found or not owned by user_id.
    Raises StaleVersionError if version does not match expected_version.
    """
    if not isinstance(portfolio_id, ObjectId) and not (
        isinstance(portfolio_id, str) and ObjectId.is_valid(portfolio_id)
    ):
        raise PortfolioNotFoundError("Portfolio not found.")

    portfolio_oid = _to_object_id(portfolio_id)
    user_oid = _to_object_id(user_id)

    try:
        expected_v = int(expected_version)
    except (TypeError, ValueError):
        raise StaleVersionError("Invalid version identifier.") from None

    res = db.portfolios.update_one(
        {"_id": portfolio_oid, "user_id": user_oid, "version": expected_v},
        {"$inc": {"version": 1}},
    )

    if res.matched_count == 1:
        return db.portfolios.find_one({"_id": portfolio_oid})

    # Differentiate 404 from 409
    doc = db.portfolios.find_one({"_id": portfolio_oid, "user_id": user_oid})
    if not doc:
        raise PortfolioNotFoundError("Portfolio not found.")
    raise StaleVersionError(
        f"Portfolio version conflict: expected {expected_v}, "
        f"current version is {doc.get('version')}."
    )


def delete_portfolio(db, portfolio_id, user_id, expected_version):
    """Delete a portfolio and all associated trades, asserting ownership and version."""
    claim_portfolio(db, portfolio_id, user_id, expected_version)
    portfolio_oid = _to_object_id(portfolio_id)
    user_oid = _to_object_id(user_id)

    db.trades.delete_many({"portfolio_id": portfolio_oid})
    db.portfolios.delete_one({"_id": portfolio_oid, "user_id": user_oid})
    return True
