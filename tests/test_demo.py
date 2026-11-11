"""Tests for demo seed and public read-only /demo page."""

import pytest

from scripts.refresh_prices import seed_demo_prices
from scripts.seed_demo import DEMO_PORTFOLIO_NAME, DEMO_TRADES, seed_demo
from sources.config import DEMO_USER_EMAIL


@pytest.fixture
def seeded_demo(db):
    """Seed demo prices, demo user, demo portfolio, and trades in test DB."""
    seed_demo_prices(db)
    portfolio_id = seed_demo(db)
    user_doc = db.users.find_one({"email": DEMO_USER_EMAIL})
    portfolio_doc = db.portfolios.find_one({"_id": portfolio_id})
    return {"user": user_doc, "portfolio": portfolio_doc}


def test_demo_missing_returns_404(client, db):
    """GET /demo and /demo/calendar return 404 when demo account or portfolio is absent."""
    res_dash = client.get("/demo")
    assert res_dash.status_code == 404

    res_cal = client.get("/demo/calendar")
    assert res_cal.status_code == 404


def test_demo_page_anonymous_200_no_forms_no_csrf(client, seeded_demo):
    """GET /demo returns 200 without login, showing banner and no forms or CSRF tokens."""
    res = client.get("/demo")
    assert res.status_code == 200

    html = res.text
    # Demo banner with eye icon and expected copy
    assert "Read-only demo." in html
    assert "Synthetic demo data. Nothing here is a real account." in html
    assert "bi-eye" in html

    # Decision 7: replaced write buttons with read-only notice
    decision_7_note = (
        'Read-only. <a href="/register" class="text-decoration-none">'
        "Create an account</a> to add or import trades."
    )
    assert decision_7_note in html

    # Absolutely no forms and no CSRF tokens on read-only demo dashboard
    assert "<form" not in html
    assert "csrf_token" not in html

    # No edit/delete/add/import action controls
    assert "Add trade" not in html
    assert "Import CSV" not in html
    assert "trade_edit" not in html
    assert "trade_delete" not in html

    # Dashboard displays portfolio name, open positions, realized lot portions, and recorded trades
    assert DEMO_PORTFOLIO_NAME in html
    assert "Open positions" in html
    assert "Realized lot portions" in html
    assert "Recorded trades" in html
    assert "/demo/calendar" in html


def test_demo_calendar_anonymous_200(client, seeded_demo):
    """GET /demo/calendar returns 200 for anonymous visitor and links back to /demo."""
    res = client.get("/demo/calendar")
    assert res.status_code == 200

    html = res.text
    assert "P/L calendar" in html
    assert "Read-only demo." in html
    assert "Synthetic demo data. Nothing here is a real account." in html
    assert "/demo" in html


def test_demo_portfolio_write_routes_rejected_anonymous(client, seeded_demo):
    """POSTs to demo write routes from anonymous user are redirected to login or rejected."""
    p_id = str(seeded_demo["portfolio"]["_id"])

    # Anonymous attempts to add trade, import, or delete trade
    res_add = client.post(f"/portfolios/{p_id}/trades/new", data={"symbol": "DEMO1"})
    assert res_add.status_code in (302, 401)
    if res_add.status_code == 302:
        assert "/login" in res_add.headers.get("Location", "")

    res_import = client.post(f"/portfolios/{p_id}/import", data={})
    assert res_import.status_code in (302, 401)
    if res_import.status_code == 302:
        assert "/login" in res_import.headers.get("Location", "")

    first_trade = seeded_demo["portfolio"]["_id"]
    res_delete = client.post(f"/portfolios/{p_id}/trades/{first_trade}/delete", data={})
    assert res_delete.status_code in (302, 401)
    if res_delete.status_code == 302:
        assert "/login" in res_delete.headers.get("Location", "")


def test_demo_portfolio_write_routes_rejected_other_user(logged_in_client, seeded_demo):
    """POSTs to demo portfolio write routes from another authenticated user return 404."""
    p_id = str(seeded_demo["portfolio"]["_id"])

    res_add = logged_in_client.post(
        f"/portfolios/{p_id}/trades/new",
        data={"symbol": "DEMO1", "side": "buy", "qty": "100", "price": "10.00"},
    )
    assert res_add.status_code == 404

    res_import = logged_in_client.post(f"/portfolios/{p_id}/import", data={})
    assert res_import.status_code == 404

    res_delete = logged_in_client.post(
        f"/portfolios/{p_id}/trades/{p_id}/delete",
        data={"version": "1"},
    )
    assert res_delete.status_code == 404


def test_demo_login_fails(client, seeded_demo):
    """Login attempts as DEMO_USER_EMAIL fail for any password due to unusable password hash."""
    for pwd in ["password123", "demo", "admin", "!", "unusable", "secret"]:
        res = client.post("/login", data={"email": DEMO_USER_EMAIL, "password": pwd})
        assert res.status_code == 200
        assert "Invalid email or password." in res.text

    # Verify user is not authenticated and cannot access protected /portfolios
    res_protected = client.get("/portfolios")
    assert res_protected.status_code == 302
    assert "/login" in res_protected.headers.get("Location", "")


def test_demo_seed_idempotent(db):
    """Running seed_demo multiple times does not duplicate users, portfolios, or trades."""
    seed_demo_prices(db)

    # First run
    p_id_1 = seed_demo(db)
    assert db.users.count_documents({"email": DEMO_USER_EMAIL}) == 1
    assert db.portfolios.count_documents({"name": DEMO_PORTFOLIO_NAME}) == 1
    assert db.trades.count_documents({"portfolio_id": p_id_1}) == len(DEMO_TRADES)

    # Second run
    p_id_2 = seed_demo(db)
    assert p_id_1 == p_id_2
    assert db.users.count_documents({"email": DEMO_USER_EMAIL}) == 1
    assert db.portfolios.count_documents({"name": DEMO_PORTFOLIO_NAME}) == 1
    assert db.trades.count_documents({"portfolio_id": p_id_1}) == len(DEMO_TRADES)


def test_home_and_navbar_demo_links_guest(client, seeded_demo):
    """Home page links to /demo as primary CTA and navbar displays Demo link for guests."""
    res_home = client.get("/")
    assert res_home.status_code == 200
    html_home = res_home.text
    # Primary CTA button
    assert 'href="/demo"' in html_home
    assert "View live demo" in html_home
    # Navbar has Demo link for guests
    assert '<a class="nav-link ' in html_home
    assert 'href="/demo">Demo</a>' in html_home


def test_navbar_demo_link_hidden_when_logged_in(logged_in_client, seeded_demo):
    """Navbar does not display Demo link for authenticated users."""
    res_logged_in = logged_in_client.get("/")
    assert res_logged_in.status_code == 200
    html_logged_in = res_logged_in.text
    assert 'href="/demo">Demo</a>' not in html_logged_in
