"""Game persistence and leaderboard repository for the market tycoon game."""

import secrets
from decimal import Decimal

from bson.decimal128 import Decimal128
from bson.objectid import ObjectId

import modules.game_engine as game_engine
from sources.functions import utcnow
from sources.money import from_d128, to_d128


class GameNotFoundError(Exception):
    """Raised when a game does not exist or belongs to another owner."""


class StaleVersionError(Exception):
    """Raised when an action write conflicts with a newer document version."""


def ensure_indexes(db):
    """Ensure indexes on games collection for ownership and leaderboard queries."""
    db.games.create_index("owner")
    db.games.create_index([("finished_at", 1), ("score", -1)])
    db.games.create_index(
        [("score", -1)],
        partialFilterExpression={"finished_at": {"$exists": True}},
    )


def serialize_state(val):
    """Recursively convert Decimal instances to Decimal128 for MongoDB storage."""
    if isinstance(val, Decimal):
        return to_d128(val)
    if isinstance(val, dict):
        return {k: serialize_state(v) for k, v in val.items()}
    if isinstance(val, list):
        return [serialize_state(v) for v in val]
    return val


def deserialize_state(val):
    """Recursively convert Decimal128 instances back to Decimal for engine calculations."""
    if isinstance(val, Decimal128):
        return from_d128(val)
    if isinstance(val, dict):
        return {k: deserialize_state(v) for k, v in val.items()}
    if isinstance(val, list):
        return [deserialize_state(v) for v in val]
    return val


def _to_object_id(val):
    if isinstance(val, ObjectId):
        return val
    if isinstance(val, str) and ObjectId.is_valid(val):
        return ObjectId(val)
    return None


def create_game(db, owner, nickname, seed=None):
    """Create a new game document with initialized engine state and version 1."""
    clean_nickname = nickname.strip() if isinstance(nickname, str) else ""
    if not (3 <= len(clean_nickname) <= 20):
        raise ValueError("Nickname must be between 3 and 20 characters.")

    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("Owner identifier is required.")

    if seed is None:
        seed = secrets.randbelow(2_000_000_000)

    initial_state = game_engine.new_game(seed)
    doc = {
        "owner": owner.strip(),
        "nickname": clean_nickname,
        "version": 1,
        "state": serialize_state(initial_state),
        "created_at": utcnow(),
    }
    result = db.games.insert_one(doc)
    return result.inserted_id


def get_game(db, game_id, owner=None):
    """Retrieve a game by ID, optionally asserting ownership.

    Deserializes state and score if present.
    """
    oid = _to_object_id(game_id)
    if not oid:
        return None

    query = {"_id": oid}
    if owner is not None:
        query["owner"] = owner

    doc = db.games.find_one(query)
    if not doc:
        return None

    if "state" in doc:
        doc["state"] = deserialize_state(doc["state"])
    if doc.get("score") is not None and isinstance(doc["score"], Decimal128):
        doc["score"] = from_d128(doc["score"])

    return doc


def apply_game_action(db, game_id, owner, action, expected_version):
    """Apply an action to the game state with optimistic concurrency check.

    Returns a tuple of (updated_game_doc, new_state).
    Raises GameNotFoundError if game does not exist or owner does not match.
    Raises StaleVersionError if version does not match expected_version.
    Raises game_engine.GameError if the action is invalid.
    """
    oid = _to_object_id(game_id)
    if not oid:
        raise GameNotFoundError("Game not found.")

    try:
        expected_v = int(expected_version)
    except (TypeError, ValueError):
        raise StaleVersionError("Invalid version identifier.") from None

    # Step 1: Read existing document asserting ownership
    doc = db.games.find_one({"_id": oid, "owner": owner})
    if not doc:
        raise GameNotFoundError("Game not found.")

    if doc.get("version") != expected_v:
        raise StaleVersionError(
            f"Game version conflict: expected {expected_v}, "
            f"current version is {doc.get('version')}."
        )

    # Step 2: Apply action to current state
    current_state = deserialize_state(doc["state"])
    new_state = game_engine.apply_action(current_state, action)

    # Step 3: Prepare update payload
    update_set = {
        "state": serialize_state(new_state),
    }
    if new_state.get("score") is not None:
        update_set["score"] = to_d128(new_state["score"])
        update_set["finished_at"] = utcnow()
        update_set["finished"] = True

    # Step 4: Atomic conditional update
    res = db.games.update_one(
        {"_id": oid, "owner": owner, "version": expected_v},
        {"$set": update_set, "$inc": {"version": 1}},
    )

    if res.matched_count == 0:
        # Check whether document was deleted or updated concurrently
        existing = db.games.find_one({"_id": oid, "owner": owner})
        if not existing:
            raise GameNotFoundError("Game not found.")
        raise StaleVersionError("Game version conflict.")

    updated_doc = db.games.find_one({"_id": oid})
    if updated_doc and "state" in updated_doc:
        updated_doc["state"] = deserialize_state(updated_doc["state"])
    if (
        updated_doc
        and updated_doc.get("score") is not None
        and isinstance(updated_doc["score"], Decimal128)
    ):
        updated_doc["score"] = from_d128(updated_doc["score"])

    return updated_doc, new_state


def get_leaderboard(db, limit=20):
    """Retrieve top finished games ordered by score descending."""
    cursor = db.games.find(
        {"finished_at": {"$exists": True}, "score": {"$ne": None}}
    ).sort([("score", -1), ("finished_at", 1)]).limit(limit)

    results = []
    for rank, doc in enumerate(cursor, start=1):
        score_val = doc.get("score")
        if isinstance(score_val, Decimal128):
            score_val = from_d128(score_val)
        results.append({
            "rank": rank,
            "nickname": doc.get("nickname", "Anonymous"),
            "score": score_val,
            "finished_at": doc.get("finished_at"),
            "game_id": str(doc["_id"]),
        })
    return results


def get_active_game_for_owner(db, owner):
    """Retrieve the most recent unfinished game for the given owner, if any."""
    doc = db.games.find_one(
        {"owner": owner, "finished_at": {"$exists": False}},
        sort=[("created_at", -1)],
    )
    if not doc:
        return None
    if "state" in doc:
        doc["state"] = deserialize_state(doc["state"])
    return doc
