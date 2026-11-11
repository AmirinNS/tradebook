import re

import pytest

from tradebook import app, limiter

CREDENTIALS = {"email": "user@example.com", "password": "password123"}


@pytest.mark.parametrize("path", ["/register", "/login", "/logout"])
def test_auth_posts_require_csrf(client, path):
    original = app.config["WTF_CSRF_ENABLED"]
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        assert client.post(path, data=CREDENTIALS).status_code == 400
    finally:
        app.config["WTF_CSRF_ENABLED"] = original


def test_csrf_forms_allow_register_logout_and_login(client):
    original = app.config["WTF_CSRF_ENABLED"]
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        for form_path, action, data in [
            ("/register", "/register", CREDENTIALS),
            ("/account", "/logout", {}),
            ("/login", "/login", CREDENTIALS),
        ]:
            page = client.get(form_path)
            token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data)
            assert token is not None
            response = client.post(action, data={**data, "csrf_token": token[1].decode()})
            assert response.status_code == 302
        assert client.get("/account").status_code == 200
    finally:
        app.config["WTF_CSRF_ENABLED"] = original


def test_sixth_login_is_rate_limited(client):
    original_enabled = limiter.enabled
    limiter.reset()
    limiter.enabled = True
    try:
        responses = [client.post("/login", data=CREDENTIALS) for _ in range(6)]
        assert [response.status_code for response in responses[:5]] == [200] * 5
        assert responses[5].status_code == 429
        assert int(responses[5].headers["Retry-After"]) > 0
    finally:
        limiter.reset()
        limiter.enabled = original_enabled


def test_cookie_security_configuration():
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["REMEMBER_COOKIE_HTTPONLY"] is True
    assert app.config["REMEMBER_COOKIE_SAMESITE"] == "Lax"
    assert app.config["REMEMBER_COOKIE_SECURE"] == app.config["SESSION_COOKIE_SECURE"]
