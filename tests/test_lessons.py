import re

import modules.lessons as lessons
import modules.progress as progress
from scripts.refresh_prices import seed_demo_prices
from scripts.seed_demo import seed_demo
from tradebook import app

EXPECTED_SLUGS = {
    "candlesticks",
    "moving-averages",
    "rsi",
    "macd",
    "position-sizing",
    "fifo-and-realized-pnl",
    "bursa-trading-costs",
    "keeping-a-journal",
}


def test_load_lessons_front_matter():
    """Verify all 8 lessons are loaded with valid front matter and sorted order."""
    all_lessons = lessons.list_lessons()
    assert len(all_lessons) == 8
    slugs = {item["slug"] for item in all_lessons}
    assert slugs == EXPECTED_SLUGS

    orders = [item["order"] for item in all_lessons]
    assert orders == list(range(1, 9))

    for item in all_lessons:
        assert item["title"]
        assert item["summary"]
        assert item["reading_time"] > 0
        assert isinstance(item["related_filters"], list)
        assert item["html"]
        assert "Educational content, not financial advice" in item["raw_body"]
        assert "Try It" in item["raw_body"] or "Try it" in item["raw_body"]


def test_lessons_contain_no_raw_latex_formulas():
    """Verify no raw LaTeX formulas ($$, \\text{, \\frac, \\times, $) remain in lessons."""
    bad_tokens = ["$$", r"\text{", r"\frac", r"\times", "$"]
    for item in lessons.list_lessons():
        raw = item["raw_body"]
        for token in bad_tokens:
            assert token not in raw, f"Found raw LaTeX token {token!r} in {item['slug']}.md"


def test_bursa_fee_lesson_cites_schedule_and_url():
    """Verify Bursa trading costs lesson cites the dated schedule and source URL."""
    lesson = lessons.get_lesson("bursa-trading-costs")
    assert lesson is not None
    assert "2026-11-11" in lesson["raw_body"]
    assert "rakutentrade.my/fees" in lesson["raw_body"]
    assert "0.03%" in lesson["raw_body"]
    assert "RM1,000" in lesson["raw_body"]


def test_get_lesson_lookup():
    """Verify get_lesson returns dict for known slug and None for unknown."""
    rsi = lessons.get_lesson("rsi")
    assert rsi is not None
    assert rsi["title"] == "RSI: Relative Strength Index"
    assert "Relative Strength Index" in rsi["html"]

    unknown = lessons.get_lesson("non-existent-lesson")
    assert unknown is None


def test_learn_index_route_guest(client):
    """Verify guests can view the /learn index with all lessons and navbar link."""
    response = client.get("/learn")
    assert response.status_code == 200
    html = response.data.decode()
    for slug in EXPECTED_SLUGS:
        assert f"/learn/{slug}" in html
    assert "Navbar" not in html
    assert 'href="/learn"' in html
    assert "Free educational curriculum" in html


def test_lesson_detail_route_guest(client):
    """Verify guests can read lessons and 404 is returned for unknown slug."""
    response = client.get("/learn/rsi")
    assert response.status_code == 200
    html = response.data.decode()
    assert "RSI: Relative Strength Index" in html
    assert "Educational content, not financial advice" in html
    assert "screener?rsi_lt=30" in html
    assert "Log in" in html

    response_404 = client.get("/learn/not-a-real-slug")
    assert response_404.status_code == 404


def test_lesson_complete_requires_login(client):
    """Verify unauthenticated POST to /learn/<slug>/complete is redirected to login."""
    response = client.post("/learn/rsi/complete")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_lesson_complete_flow_and_idempotence(logged_in_client, db):
    """Verify completing a lesson records progress and completing twice stays one record."""
    user = db.users.find_one({"email": "user@example.com"})
    assert user is not None
    user_id = user["_id"]

    # Initial state: 0 completed
    assert progress.progress(db, user_id) == set()

    # Complete rsi
    response = logged_in_client.post("/learn/rsi/complete")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/learn/rsi")

    # Verify progress recorded
    completed = progress.progress(db, user_id)
    assert completed == {"rsi"}
    assert db.lesson_progress.count_documents({"user_id": user_id, "slug": "rsi"}) == 1

    # Complete rsi again (idempotent)
    response_again = logged_in_client.post("/learn/rsi/complete")
    assert response_again.status_code == 302
    assert db.lesson_progress.count_documents({"user_id": user_id, "slug": "rsi"}) == 1

    # Verify detail page shows completed badge
    detail_res = logged_in_client.get("/learn/rsi")
    assert detail_res.status_code == 200
    assert "You have completed this lesson" in detail_res.data.decode()

    # Verify index page reflects progress
    index_res = logged_in_client.get("/learn")
    assert index_res.status_code == 200
    assert "lessons completed" in index_res.data.decode()
    assert "1</span> of <span class=\"tb-num\">8</span>" in index_res.data.decode()


def test_lesson_complete_unknown_slug_404(logged_in_client):
    """Verify POST /learn/<slug>/complete for unknown slug returns 404."""
    response = logged_in_client.post("/learn/invalid-slug/complete")
    assert response.status_code == 404


def test_lesson_complete_csrf_protection(logged_in_client):
    """Verify POST /learn/<slug>/complete requires CSRF token when enabled."""
    original = app.config["WTF_CSRF_ENABLED"]
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        # POST without token fails
        fail_res = logged_in_client.post("/learn/candlesticks/complete")
        assert fail_res.status_code == 400

        # Fetch page with token and post successfully
        page = logged_in_client.get("/learn/candlesticks")
        token_match = re.search(rb'name="csrf_token" value="([^"]+)"', page.data)
        assert token_match is not None
        csrf_token = token_match.group(1).decode()

        ok_res = logged_in_client.post(
            "/learn/candlesticks/complete",
            data={"csrf_token": csrf_token},
        )
        assert ok_res.status_code == 302
    finally:
        app.config["WTF_CSRF_ENABLED"] = original


def test_screener_links_to_matching_lessons(client):
    """Verify screener filter labels link to RSI, Moving Averages, and MACD lessons."""
    response = client.get("/screener")
    assert response.status_code == 200
    html = response.data.decode()
    assert 'href="/learn/rsi"' in html
    assert 'href="/learn/moving-averages"' in html
    assert 'href="/learn/macd"' in html


def test_journal_summary_cards_link_to_lessons(client, db):
    """Verify demo journal metric cards link to FIFO and journal lessons."""
    seed_demo_prices(db)
    seed_demo(db)
    response = client.get("/demo")
    assert response.status_code == 200
    html = response.data.decode()
    assert 'href="/learn/fifo-and-realized-pnl"' in html
    assert 'href="/learn/keeping-a-journal"' in html
    assert 'href="/learn/bursa-trading-costs"' in html


def test_sitemap_includes_lessons(client):
    """Verify sitemap.xml includes /learn and all lesson URLs."""
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    xml = response.data.decode()
    assert "/learn" in xml
    for slug in EXPECTED_SLUGS:
        assert f"/learn/{slug}" in xml
