import os

import pymongo
from dotenv import load_dotenv

load_dotenv()

# Run mode: development | testing | production
#   development — native Flask server, debug on
#   testing     — native Flask server, debug on
#   production  — waitress WSGI server, debug off
APP_ENV = os.environ.get("APP_ENV", "development").lower()
IS_PRODUCTION = APP_ENV == "production"
DEBUG = not IS_PRODUCTION

# The app and its MongoDB are assumed co-located (same host). Set MONGO_URI
# per environment in .env; testing may point at a remote/shared DB.
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "tradebook")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
PORT = int(os.environ.get("PORT", 5000))
RATELIMIT_ENABLED = os.environ.get("RATELIMIT_ENABLED", "true").strip().lower() in {
    "1", "true", "yes", "on"
}

INSECURE_SECRET_KEYS = {
    "dev-secret-change-me",
    "change-me-in-production",
}

if IS_PRODUCTION:
    if not SECRET_KEY or SECRET_KEY.strip() in INSECURE_SECRET_KEYS:
        raise RuntimeError(
            f"Invalid SECRET_KEY in production: {SECRET_KEY!r}. "
            "Please configure a strong, unique SECRET_KEY in your environment."
        )

# Cookie security: default True in production, False otherwise.
# Can be explicitly set via COOKIE_SECURE environment variable (e.g. for local HTTP Docker Compose).
_raw_cookie_secure = os.environ.get("COOKIE_SECURE")
if _raw_cookie_secure is not None:
    COOKIE_SECURE = _raw_cookie_secure.strip().lower() in {"1", "true", "yes", "on"}
else:
    COOKIE_SECURE = IS_PRODUCTION

# Site identity — used for SEO meta tags, canonical URLs, robots/sitemap.
SITE_NAME = os.environ.get("SITE_NAME", "tradebook")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:5000").rstrip("/")
DEMO_USER_EMAIL = os.environ.get("DEMO_USER_EMAIL", "demo@example.com").strip().lower()

_client = pymongo.MongoClient(MONGO_URI)
db = _client[DB_NAME]
