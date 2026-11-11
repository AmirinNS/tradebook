"""CSV preview/confirm and calendar route integration checks."""

import importlib
import io
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from bson.objectid import ObjectId

from modules import csv_import, imports, portfolios, trades


def portfolio_for_client(logged_in_client, db):
    user = db.users.find_one({"email": "user@example.com"})
    return portfolios.create_portfolio(db, user["_id"], "CSV book")


def upload(client, portfolio_id, contents):
    return client.post(
        f"/portfolios/{portfolio_id}/import",
        data={"file": (io.BytesIO(contents), "trades.csv")},
        content_type="multipart/form-data",
    )


def test_csv_fixture_preview_and_confirm_end_to_end(logged_in_client, db):
    portfolio_id = portfolio_for_client(logged_in_client, db)
    path = f"/portfolios/{portfolio_id}"
    dashboard = logged_in_client.get(path)
    assert f'{path}/calendar'.encode() in dashboard.data
    assert f'{path}/import'.encode() in dashboard.data
    assert logged_in_client.get(f"{path}/import").status_code == 200
    contents = (Path(__file__).parent / "fixtures" / "sample_trades.csv").read_bytes()
    response = upload(logged_in_client, portfolio_id, contents)
    assert response.status_code == 200
    assert b"Confirm import" in response.data
    assert db.trades.count_documents({}) == 0
    preview = db.import_previews.find_one({"portfolio_id": portfolio_id})
    with logged_in_client.session_transaction() as session:
        assert "rows" not in session
        assert "DEMO1" not in str(dict(session))
    for _ in range(2):
        response = logged_in_client.post(f"/imports/{preview['_id']}/confirm")
        assert response.status_code == 302
    assert db.trades.count_documents({"portfolio_id": portfolio_id}) == len(preview["rows"])


def test_errors_show_line_numbers_and_block_confirmation(logged_in_client, db):
    portfolio_id = portfolio_for_client(logged_in_client, db)
    response = upload(
        logged_in_client, portfolio_id,
        b"date,symbol,side,qty,price,fees\n2026-11-01,DEMO1,buy,10,10,0\nbad,DEMO1,buy,1,10,0\n",
    )
    assert response.status_code == 400
    assert b"Line 3" in response.data
    assert b"Preview trades" in response.data
    assert b"Confirm import" not in response.data
    assert db.import_previews.count_documents({}) == 0
    assert db.trades.count_documents({}) == 0


@pytest.mark.parametrize(
    "contents, status", [(b"\xff\xfe", 400), (b"x" * (csv_import.MAX_BYTES + 1), 413)],
)
def test_upload_boundaries(logged_in_client, db, contents, status):
    portfolio_id = portfolio_for_client(logged_in_client, db)
    assert upload(logged_in_client, portfolio_id, contents).status_code == status
    assert db.import_previews.count_documents({}) == 0


def test_foreign_preview_and_portfolio_are_404(logged_in_client, db):
    portfolio_id = portfolios.create_portfolio(db, ObjectId(), "Private book")
    assert logged_in_client.get(f"/portfolios/{portfolio_id}/import").status_code == 404
    assert upload(logged_in_client, portfolio_id, b"csv").status_code == 404
    assert logged_in_client.get(f"/portfolios/{portfolio_id}/calendar").status_code == 404
    owner_id = db.portfolios.find_one({"_id": portfolio_id})["user_id"]
    preview_id = db.import_previews.insert_one({
        "user_id": owner_id, "portfolio_id": portfolio_id,
        "status": "pending", "rows": [],
    }).inserted_id
    assert logged_in_client.post(f"/imports/{preview_id}/confirm").status_code == 404
    assert logged_in_client.post("/imports/invalid/confirm").status_code == 404


def test_calendar_shows_daily_net_totals_and_accessible_signs(logged_in_client, db):
    portfolio_id = portfolio_for_client(logged_in_client, db)
    response = upload(
        logged_in_client, portfolio_id,
        b"date,symbol,side,qty,price,fees\n"
        b"2026-10-31,DEMO1,buy,10,10,2\n"
        b"2026-11-02,DEMO1,sell,4,12,1\n"
        b"2026-11-02,DEMO1,sell,2,13,1\n"
        b"2026-11-03,DEMO1,sell,4,9,1\n",
    )
    assert response.status_code == 200
    preview = db.import_previews.find_one({"portfolio_id": portfolio_id})
    assert logged_in_client.post(f"/imports/{preview['_id']}/confirm").status_code == 302
    response = logged_in_client.get(f"/portfolios/{portfolio_id}/calendar?year=2026&month=11")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    # Independent arithmetic: November 2 gross gain 14, buy fees 1.20, sell fees 2.
    assert "▲</span> +10.80" in text
    assert "▼</span> -5.80" in text
    assert 'visually-hidden"> gain' in text
    assert 'visually-hidden"> loss' in text
    assert "November 2026" in text
    assert "MYR portfolio" in text
    assert 'datetime="2026-11-02"' in text
    assert "Monday" in text


@pytest.mark.parametrize("query", ["year=0&month=1", "year=2026&month=13", "year=no&month=1"])
def test_invalid_calendar_parameters(logged_in_client, db, query):
    portfolio_id = portfolio_for_client(logged_in_client, db)
    assert logged_in_client.get(f"/portfolios/{portfolio_id}/calendar?{query}").status_code == 400


@pytest.fixture
def unit_client(monkeypatch):
    # Startup index creation is the only database operation during module import.
    with patch("sources.indexes.ensure_all_indexes"):
        application = importlib.import_module("tradebook")
    for key, value in {"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False}.items():
        monkeypatch.setitem(application.app.config, key, value)
    monkeypatch.setattr(application.limiter, "enabled", False)
    monkeypatch.setattr(application, "current_user", Mock(get_id=lambda: str(ObjectId())))
    database = Mock()
    database.portfolios.find_one.return_value = {
        "_id": ObjectId(), "user_id": ObjectId(), "name": "CSV book", "currency": "MYR",
    }
    monkeypatch.setattr(application, "db", database)
    with application.app.test_client() as client:
        yield client, database


def test_unit_upload_errors_render_valid_rows_without_confirm(unit_client):
    client, database = unit_client
    response = upload(
        client, ObjectId(),
        b"date,symbol,side,qty,price,fees\n2026-11-01,DEMO1,buy,10,10,0\nbad,DEMO1,buy,1,10,0\n",
    )
    assert response.status_code == 400
    assert b"Line 3" in response.data
    assert b"10.0000" in response.data
    assert b"Confirm import" not in response.data
    database.import_previews.insert_one.assert_not_called()


def test_unit_upload_stores_preview_and_sends_only_id(unit_client):
    client, database = unit_client
    preview_id = ObjectId()
    database.import_previews.insert_one.return_value.inserted_id = preview_id
    contents = (Path(__file__).parent / "fixtures" / "sample_trades.csv").read_bytes()
    response = upload(client, ObjectId(), contents)
    assert response.status_code == 200
    assert f'/imports/{preview_id}/confirm'.encode() in response.data
    assert b'name="rows"' not in response.data
    assert b"Confirm import" in response.data
    database.import_previews.insert_one.assert_called_once()
    database.trades.insert_many.assert_not_called()
    with client.session_transaction() as session:
        assert "rows" not in session


@pytest.mark.parametrize(
    "contents, status", [(b"\xff\xfe", 400), (b"x" * (csv_import.MAX_BYTES + 1), 413)],
)
def test_unit_upload_boundaries(unit_client, contents, status):
    client, database = unit_client
    assert upload(client, ObjectId(), contents).status_code == status
    database.import_previews.insert_one.assert_not_called()


def test_unit_calendar_renders_actual_ledger_totals(unit_client):
    client, database = unit_client
    rows, errors = csv_import.parse_trades_csv(
        "date,symbol,side,qty,price,fees\n"
        "2026-10-31,DEMO1,buy,10,10,2\n"
        "2026-11-02,DEMO1,sell,4,12,1\n"
        "2026-11-02,DEMO1,sell,2,13,1\n"
        "2026-11-03,DEMO1,sell,4,9,1\n"
    )
    assert not errors
    # Use the same persisted Decimal128 shape that the route reads from Mongo.
    from_rows = []
    for seq, row in enumerate(rows):
        trade = imports.Trade(portfolio_id=ObjectId(), seq=seq, **row)
        from_rows.append(trades._trade_to_doc(trade))
    database.trades.find.return_value.sort.return_value = from_rows
    response = client.get(f"/portfolios/{ObjectId()}/calendar?year=2026&month=11")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "▲</span> +10.80" in text
    assert "▼</span> -5.80" in text
    assert 'visually-hidden"> gain' in text
    assert 'visually-hidden"> loss' in text
    assert "November 2026" in text
