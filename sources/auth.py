"""Flask-Login session wiring and relative redirect validation."""

from urllib.parse import urlsplit

from bson.objectid import ObjectId
from flask_login import LoginManager, UserMixin

from sources.config import db

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message_category = "warning"


class User(UserMixin):
    """Thin Mongo document wrapper required by Flask-Login."""

    def __init__(self, doc):
        self.doc = doc

    def get_id(self):
        return str(self.doc["_id"])

    @property
    def email(self):
        return self.doc["email"]


@login_manager.user_loader
def load_user(user_id):
    if not ObjectId.is_valid(user_id):
        return None
    doc = db.users.find_one({"_id": ObjectId(user_id)})
    return User(doc) if doc else None


def init_login(app):
    login_manager.init_app(app)


def safe_next(target):
    """Accept root-relative paths without browser URL normalization ambiguities."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return None
    if "\\" in target or any(ord(character) < 32 or ord(character) == 127 for character in target):
        return None
    parsed = urlsplit(target)
    return target if not parsed.scheme and not parsed.netloc else None
