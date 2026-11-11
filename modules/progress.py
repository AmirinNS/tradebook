"""Track educational lesson progress per user."""

from bson.objectid import ObjectId

from sources.functions import utcnow


def ensure_indexes(db):
    """Ensure indexes on lesson_progress collection."""
    db.lesson_progress.create_index([("user_id", 1), ("slug", 1)], unique=True)


def _to_user_id(user_id):
    if isinstance(user_id, ObjectId):
        return user_id
    if isinstance(user_id, str) and ObjectId.is_valid(user_id):
        return ObjectId(user_id)
    return user_id


def mark_complete(db, user_id, slug):
    """Mark a lesson as completed for user_id. Idempotent."""
    uid = _to_user_id(user_id)
    now = utcnow()
    db.lesson_progress.update_one(
        {"user_id": uid, "slug": slug},
        {"$setOnInsert": {"user_id": uid, "slug": slug, "completed_at": now}},
        upsert=True,
    )


def progress(db, user_id):
    """Return set of completed lesson slugs for user_id."""
    if not user_id:
        return set()
    uid = _to_user_id(user_id)
    docs = db.lesson_progress.find({"user_id": uid}, {"slug": 1})
    return {doc["slug"] for doc in docs}


# Alias for callers expecting get_progress
get_progress = progress
