from urllib.parse import parse_qs, urlsplit

import pytest
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash

import modules.users as users
from sources.auth import load_user

CREDENTIALS = {"email": "user@example.com", "password": "password123"}


def test_register_signs_in_and_hashes_password(client, db):
    response = client.post(
        "/register",
        data={**CREDENTIALS, "email": " User@Example.com "},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"user@example.com" in response.data
    doc = db.users.find_one({"email": CREDENTIALS["email"]})
    assert doc is not None
    assert "password" not in doc
    assert doc["password_hash"] != CREDENTIALS["password"]
    assert check_password_hash(doc["password_hash"], CREDENTIALS["password"])
    assert client.get("/account").status_code == 200


def test_duplicate_email_uses_unique_index(client, db):
    client.post("/register", data=CREDENTIALS)
    client.post("/logout")
    response = client.post("/register", data={**CREDENTIALS, "email": "USER@EXAMPLE.COM"})
    assert b"already registered" in response.data
    assert db.users.count_documents({}) == 1
    with pytest.raises(DuplicateKeyError):
        users.create_user(db, " User@Example.com ", CREDENTIALS["password"])


@pytest.mark.parametrize("email", ["user@example.com", "missing@example.com"])
def test_bad_login_is_generic(client, db, email):
    users.create_user(db, **CREDENTIALS)
    response = client.post("/login", data={"email": email, "password": "wrong-password"})
    assert b"Invalid email or password." in response.data
    assert client.get("/account").status_code == 302


def test_login_logout_and_protected_page(client):
    response = client.get("/account")
    assert response.status_code == 302
    location = urlsplit(response.headers["Location"])
    assert location.path == "/login"
    assert parse_qs(location.query)["next"] == ["/account"]
    client.post("/register", data=CREDENTIALS)
    assert client.get("/logout").status_code == 405
    assert client.get("/account").status_code == 200
    assert client.post("/logout").status_code == 302
    assert client.get("/account").status_code == 302
    response = client.post(
        "/login", data={**CREDENTIALS, "email": " USER@EXAMPLE.COM "}
    )
    assert response.status_code == 302
    assert client.get("/account").status_code == 200


@pytest.mark.parametrize(
    ("target", "destination"),
    [
        ("/account?tab=profile", "/account?tab=profile"),
        ("https://example.com/", "/"),
        ("//example.com/", "/"),
        ("///example.com/", "/"),
        ("/\\example.com/", "/"),
        ("\t//example.com/", "/"),
        ("javascript:alert(1)", "/"),
        ("account", "/"),
    ],
)
def test_login_next_only_accepts_relative_paths(client, db, target, destination):
    users.create_user(db, **CREDENTIALS)
    response = client.post("/login", query_string={"next": target}, data=CREDENTIALS)
    assert response.status_code == 302
    assert response.headers["Location"] == destination


@pytest.mark.parametrize(
    ("email", "password", "message"),
    [
        ("", "password123", b"Email and password are required."),
        ("user@example.com", "", b"Email and password are required."),
        ("invalid", "password123", b"Enter a valid email address."),
        ("a" * 255 + "@example.com", "password123", b"Enter a valid email address."),
        ("user@example.com", "short", b"Password must be at least 8 characters."),
        ("user@example.com", "x" * 1025, b"Password must be at most 1024 characters."),
    ],
)
def test_registration_validation(client, db, email, password, message):
    response = client.post("/register", data={"email": email, "password": password})
    assert message in response.data
    assert db.users.count_documents({}) == 0


def test_invalid_user_id_does_not_query_mongo():
    assert load_user("invalid-id") is None
