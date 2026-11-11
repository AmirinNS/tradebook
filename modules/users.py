"""User persistence and password checks with explicit database access."""

import re

from werkzeug.security import check_password_hash, generate_password_hash

from sources.functions import utcnow


def ensure_indexes(db):
    """Keep normalized email addresses unique, including after test resets."""
    db.users.create_index("email", unique=True)


def create_user(db, email, password):
    """Validate credentials and insert a user, raising on invalid or duplicate input."""
    email = email.strip().lower()
    if not email or not password:
        raise ValueError("Email and password are required.")
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Enter a valid email address.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(password) > 1024:
        raise ValueError("Password must be at most 1024 characters.")
    doc = {
        "email": email,
        "password_hash": generate_password_hash(password),
        "created_at": utcnow(),
    }
    return db.users.insert_one(doc).inserted_id


def get_by_email(db, email):
    return db.users.find_one({"email": email.strip().lower()})


def verify_password(user_doc, password):
    if not user_doc or len(password) > 1024:
        return False
    return check_password_hash(user_doc["password_hash"], password)
