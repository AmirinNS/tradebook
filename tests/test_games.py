"""Tests for Phase G: game persistence, routes, UI, and leaderboard."""

import re
from decimal import Decimal

from bson.decimal128 import Decimal128

import modules.games as games
from sources.functions import utcnow
from sources.money import to_d128
from tradebook import app


def _create_guest_game(client, nickname="TesterBob"):
    """Helper to start a game as a guest and return (game_id, response)."""
    res = client.post("/play", data={"nickname": nickname}, follow_redirects=False)
    assert res.status_code == 302
    match = re.search(r"/play/([0-9a-fA-F]{24})", res.headers["Location"])
    assert match is not None
    game_id = match.group(1)
    return game_id


def test_nickname_validation_and_start_game(client, db):
    """Test /play nickname length constraints and game document creation."""
    # GET /play renders start page
    res = client.get("/play")
    assert res.status_code == 200
    assert b"Start a 30-day tycoon game" in res.data

    # Too short nickname (< 3 chars)
    res = client.post("/play", data={"nickname": "AB"}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Nickname must be between 3 and 20 characters." in res.data

    # Too long nickname (> 20 chars)
    res = client.post("/play", data={"nickname": "A" * 21}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Nickname must be between 3 and 20 characters." in res.data

    # Valid nickname starts game and sets guest session
    game_id = _create_guest_game(client, nickname="BullTrader")
    doc = db.games.find_one({"_id": games._to_object_id(game_id)})
    assert doc is not None
    assert doc["nickname"] == "BullTrader"
    assert doc["version"] == 1
    assert doc["owner"].startswith("guest:")
    assert isinstance(doc["state"]["cash"], Decimal128)
    assert doc["state"]["day"] == 1


def test_cross_owner_isolation_guest_and_user(client, db):
    """Other guest sessions and other authenticated users receive 404 on read and action."""
    # Guest 1 creates a game
    game_id = _create_guest_game(client, nickname="GuestOne")

    # Guest 1 can access the game and take action
    res = client.get(f"/play/{game_id}")
    assert res.status_code == 200
    assert b"Play the market" in res.data

    res = client.post(
        f"/api/play/{game_id}/action",
        json={"action": {"type": "next_day"}, "version": 1},
    )
    assert res.status_code == 200
    assert res.json["day"] == 2

    # Guest 2 (clear session to simulate a new anonymous guest session)
    with client.session_transaction() as sess:
        sess.clear()
    assert client.get(f"/play/{game_id}").status_code == 404
    assert client.post(
        f"/api/play/{game_id}/action",
        json={"action": {"type": "next_day"}, "version": 2},
    ).status_code == 404

    # User 1 registers and logs in
    client.post("/register", data={"email": "u1@example.com", "password": "password123"})
    client.post("/login", data={"email": "u1@example.com", "password": "password123"})

    # User 1 cannot access Guest 1's game
    assert client.get(f"/play/{game_id}").status_code == 404
    assert client.post(
        f"/api/play/{game_id}/action",
        json={"action": {"type": "next_day"}, "version": 2},
    ).status_code == 404

    # User 1 creates their own game
    u1_game_id = _create_guest_game(client, nickname="UserOneTrader")
    u1_doc = db.games.find_one({"_id": games._to_object_id(u1_game_id)})
    assert u1_doc["owner"].startswith("user:")

    # User 1 logs out; User 2 registers and logs in
    client.post("/logout")
    client.post("/register", data={"email": "u2@example.com", "password": "password123"})
    client.post("/login", data={"email": "u2@example.com", "password": "password123"})

    # User 2 cannot access User 1's game
    assert client.get(f"/play/{u1_game_id}").status_code == 404
    assert client.post(
        f"/api/play/{u1_game_id}/action",
        json={"action": {"type": "next_day"}, "version": 1},
    ).status_code == 404

    # User 2 logs out; anonymous guest cannot access User 1's game
    client.post("/logout")
    with client.session_transaction() as sess:
        sess.clear()
    assert client.get(f"/play/{u1_game_id}").status_code == 404
    assert client.post(
        f"/api/play/{u1_game_id}/action",
        json={"action": {"type": "next_day"}, "version": 1},
    ).status_code == 404


def test_stale_version_returns_409(client, db):
    """Actions submitted with an outdated version return 409 conflict."""
    game_id = _create_guest_game(client, nickname="VersionTester")

    # Action 1: Advance day using correct version 1
    res = client.post(
        f"/api/play/{game_id}/action",
        json={"action": {"type": "next_day"}, "version": 1},
    )
    assert res.status_code == 200
    assert res.json["version"] == 2
    assert res.json["day"] == 2

    # Action 2: Retry with stale version 1
    res_stale = client.post(
        f"/api/play/{game_id}/action",
        json={"action": {"type": "next_day"}, "version": 1},
    )
    assert res_stale.status_code == 409

    # Verify DB state is intact at version 2
    doc = db.games.find_one({"_id": games._to_object_id(game_id)})
    assert doc["version"] == 2
    assert doc["state"]["day"] == 2


def test_retrying_final_action_does_not_change_score(client, db):
    """Retrying the final action or acting after completion does not alter score."""
    game_id = _create_guest_game(client, nickname="Finisher")

    # Advance 28 times from day 1 to day 29
    version = 1
    for _day in range(1, 29):
        res = client.post(
            f"/api/play/{game_id}/action",
            json={"action": {"type": "next_day"}, "version": version},
        )
        assert res.status_code == 200
        version = res.json["version"]

    # Now at Day 29. Next day move is the final action that finishes the game on Day 30.
    final_res = client.post(
        f"/api/play/{game_id}/action",
        json={"action": {"type": "next_day"}, "version": version},
    )
    assert final_res.status_code == 200
    assert final_res.json["day"] == 30
    assert final_res.json["finished"] is True
    initial_score = final_res.json["score"]
    assert initial_score is not None

    # Verify score in DB
    doc = db.games.find_one({"_id": games._to_object_id(game_id)})
    assert doc.get("score") is not None
    db_score = doc["score"]
    assert doc.get("finished_at") is not None

    # Retry the final action with the stale version (version 29) -> 409
    stale_retry = client.post(
        f"/api/play/{game_id}/action",
        json={"action": {"type": "next_day"}, "version": version},
    )
    assert stale_retry.status_code == 409

    # Retry the final action with the new version (version 30) -> 400 (GameError: game has finished)
    new_retry = client.post(
        f"/api/play/{game_id}/action",
        json={"action": {"type": "next_day"}, "version": final_res.json["version"]},
    )
    assert new_retry.status_code == 400

    # Score remains strictly unchanged
    doc_after = db.games.find_one({"_id": games._to_object_id(game_id)})
    assert doc_after["score"] == db_score


def test_response_json_has_no_future_prices(client, db):
    """Action response JSON exposes no future prices, future news, or engine seed."""
    game_id = _create_guest_game(client, nickname="PrivacyTester")

    # Check Day 1 public view
    res = client.get(f"/play/{game_id}")
    assert res.status_code == 200

    # Advance to Day 3
    client.post(f"/api/play/{game_id}/action", json={"action": {"type": "next_day"}, "version": 1})
    res = client.post(
        f"/api/play/{game_id}/action",
        json={"action": {"type": "next_day"}, "version": 2},
    )
    assert res.status_code == 200
    data = res.json

    assert data["day"] == 3
    assert data["total_days"] == 30

    # No engine internal seed or full 30-day prices matrix
    assert "seed" not in data
    assert "prices" not in data

    # Visible history must contain exactly 3 items per symbol, never future days
    assert "history" in data
    for symbol, hist in data["history"].items():
        assert len(hist) == 3, f"History for {symbol} has {len(hist)} items, expected 3"

    # Companies only has today's price (scalar)
    assert "companies" in data
    assert len(data["companies"]) == 6
    for comp in data["companies"]:
        assert isinstance(comp["price"], str)
        assert "prices" not in comp

    # News must have exactly 3 items
    assert "news" in data
    assert len(data["news"]) == 3


def test_leaderboard_ordering(client, db):
    """Leaderboard returns top 20 finished games ordered by score descending."""
    now = utcnow()

    # Seed 25 finished games with known scores
    for i in range(25):
        score_val = Decimal("10000.00") + Decimal(i * 100)
        db.games.insert_one({
            "owner": f"guest:seeded_{i}",
            "nickname": f"Trader_{i:02d}",
            "version": 30,
            "score": to_d128(score_val),
            "finished_at": now,
            "created_at": now,
        })

    # Seed an unfinished game (should not appear on leaderboard)
    db.games.insert_one({
        "owner": "guest:unfinished",
        "nickname": "IncompleteGuy",
        "version": 5,
        "score": None,
        "created_at": now,
    })

    # Query leaderboard endpoint
    res = client.get("/play/leaderboard")
    assert res.status_code == 200
    assert b"Tycoon leaderboard" in res.data
    assert b"IncompleteGuy" not in res.data

    # Query via helper / API
    board = games.get_leaderboard(db, limit=20)
    assert len(board) == 20

    # Assert descending order
    scores = [item["score"] for item in board]
    assert scores == sorted(scores, reverse=True)

    # #1 should be the highest score (Trader_24 with 12400.00)
    assert board[0]["nickname"] == "Trader_24"
    assert board[0]["score"] == Decimal("12400.00")
    assert board[0]["rank"] == 1


def test_game_trading_actions_and_validation(client, db):
    """Test buy, sell, repay actions and their validation boundaries."""
    game_id = _create_guest_game(client, nickname="ActiveTrader")
    version = 1

    # Buy 100 shares of PEL (PEL starts around 18.0000, ~1800 total)
    res = client.post(
        f"/api/play/{game_id}/action",
        json={"action": {"type": "buy", "symbol": "PEL", "qty": 100}, "version": version},
    )
    assert res.status_code == 200
    assert res.json["holdings"]["PEL"] == 100
    version = res.json["version"]

    # Attempt to sell more than held (sell 200 PEL) -> 400
    res_oversell = client.post(
        f"/api/play/{game_id}/action",
        json={"action": {"type": "sell", "symbol": "PEL", "qty": 200}, "version": version},
    )
    assert res_oversell.status_code == 400
    assert "cannot sell more" in res_oversell.json["error"]

    # Sell 50 PEL -> succeeds
    res_sell = client.post(
        f"/api/play/{game_id}/action",
        json={"action": {"type": "sell", "symbol": "PEL", "qty": 50}, "version": version},
    )
    assert res_sell.status_code == 200
    assert res_sell.json["holdings"]["PEL"] == 50
    version = res_sell.json["version"]

    # Repay loan RM500.00
    res_repay = client.post(
        f"/api/play/{game_id}/action",
        json={"action": {"type": "repay", "amount": "500.00"}, "version": version},
    )
    assert res_repay.status_code == 200
    assert Decimal(res_repay.json["principal"]) == Decimal("9500.00")


def test_csrf_header_protection_on_action(client, db):
    """When CSRF is enabled, requests require the X-CSRFToken header."""
    game_id = _create_guest_game(client, nickname="CsrfChecker")

    original_csrf = app.config["WTF_CSRF_ENABLED"]
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        # Action without CSRF token header fails with 400
        res = client.post(
            f"/api/play/{game_id}/action",
            json={"action": {"type": "next_day"}, "version": 1},
        )
        assert res.status_code == 400

        # Retrieve page to extract CSRF token
        page = client.get(f"/play/{game_id}")
        match = re.search(r'data-csrf="([^"]+)"', page.text)
        assert match is not None
        csrf_token = match.group(1)

        # Action with header succeeds
        res_ok = client.post(
            f"/api/play/{game_id}/action",
            headers={"X-CSRFToken": csrf_token},
            json={"action": {"type": "next_day"}, "version": 1},
        )
        assert res_ok.status_code == 200
        assert res_ok.json["day"] == 2
    finally:
        app.config["WTF_CSRF_ENABLED"] = original_csrf
