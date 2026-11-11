import os
import sys
from pathlib import Path

import pytest

# Add repository root to Python path so application modules are importable
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Set testing environment variables before importing any application modules
os.environ["APP_ENV"] = "testing"
os.environ["MONGO_URI"] = os.environ.get("TEST_MONGO_URI", "mongodb://localhost:27017")
os.environ["DB_NAME"] = "tradebook_test"

from sources.config import db as config_db  # noqa: E402
from sources.indexes import ensure_all_indexes  # noqa: E402
from tradebook import app, limiter  # noqa: E402


@pytest.fixture
def db():
    """Assert connected DB ends with _test, clean collections, and ensure indexes."""
    assert config_db.name.endswith(
        "_test"
    ), f"Database name {config_db.name!r} must end with '_test'"
    for name in config_db.list_collection_names():
        if not name.startswith("system."):
            config_db[name].delete_many({})
    ensure_all_indexes(config_db)
    return config_db


@pytest.fixture
def client(db):
    """Test client with CSRF and rate limiting disabled."""
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    original_enabled = limiter.enabled
    limiter.enabled = False
    try:
        with app.test_client() as test_client:
            yield test_client
    finally:
        limiter.enabled = original_enabled


@pytest.fixture
def logged_in_client(client):
    """Test client with a registered and logged-in user."""
    email = "user@example.com"
    password = "password123"
    client.post("/register", data={"email": email, "password": password})
    client.post("/login", data={"email": email, "password": password})
    return client
