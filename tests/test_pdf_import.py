"""Synthetic PDF parsing and the existing server-side preview/confirm flow."""

import importlib
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from unittest.mock import Mock, patch

import pytest
from bson.objectid import ObjectId

from modules import imports, pdf_import, portfolios, trades
from sources.money import from_d128
from tests.fixtures.make_contract_note import make_contract_note


@pytest.mark.parametrize("side, net", [("buy", "1009.94"), ("sell", "990.06")])
def test_parse_buy_and_sell(side, net):
    rows, note = pdf_import.parse_contract_note(make_contract_note(side=side))
    assert rows == [{
        "symbol": "DEMO1", "side": side, "qty": 100,
        "price": Decimal("10.0000"), "fees": Decimal("9.94"),
        "date": datetime(2026, 11, 2, tzinfo=timezone.utc), "source": "pdf",
    }]
    assert note["contract_number"] == "SYN-2026-0001"
    assert note["stock_name"] == "Fictional Demo Shares"
    assert note["settlement_date"] == date(2026, 11, 4)
    # Independent totals: 100 * 10 = 1000; 8 + .30 + 1 + .64 = 9.94.
    assert note["gross"] == Decimal("1000.00")
    assert note["net"] == note["expected_net"] == Decimal(net)
    assert note["requires_acknowledgement"] is False


@pytest.mark.parametrize("net, mismatch", [
    ("1009.93", False), ("1009.95", False), ("1009.92", True), ("1009.96", True),
])
def test_reconciliation_tolerance(net, mismatch):
    _, note = pdf_import.parse_contract_note(make_contract_note(**{"Net amount (RM)": net}))
    assert note["requires_acknowledgement"] is mismatch


def test_gross_rounds_to_sen_before_reconciliation():
    rows, note = pdf_import.parse_contract_note(make_contract_note(**{
        "Quantity": "3", "Price (RM)": "0.3333", "Brokerage (RM)": "0",
        "Clearing fee (RM)": "0", "Stamp duty (RM)": "0", "Tax (RM)": "0",
        "Net amount (RM)": "1.00",
    }))
    assert rows[0]["price"] == Decimal("0.3333")
    assert note["gross"] == note["expected_net"] == Decimal("1.00")
    assert note["requires_acknowledgement"] is False


def test_sell_net_can_be_negative_when_fees_exceed_gross():
    _, note = pdf_import.parse_contract_note(make_contract_note(side="sell", **{
        "Brokerage (RM)": "2000.00", "Clearing fee (RM)": "0",
        "Stamp duty (RM)": "0", "Tax (RM)": "0", "Net amount (RM)": "-1000.00",
    }))
    assert note["expected_net"] == Decimal("-1000.00")
    assert note["requires_acknowledgement"] is False


@pytest.mark.parametrize("payload", [b"", b"plain text", b"\x89PNG", b"\n%PDF-1.4"])
def test_non_pdf_rejected(payload):
    with pytest.raises(ValueError, match="%PDF-"):
        pdf_import.parse_contract_note(payload)


def test_oversized_pdf_rejected_before_opening():
    with patch.object(pdf_import.pdfplumber, "open") as opened:
        with pytest.raises(ValueError, match="5 MB"):
            pdf_import.parse_contract_note(b"%PDF-" + b"x" * pdf_import.MAX_BYTES)
        opened.assert_not_called()


def test_ten_pages_accepted_and_eleven_pages_rejected():
    assert pdf_import.parse_contract_note(make_contract_note(pages=10))[0][0]["qty"] == 100
    with pytest.raises(ValueError, match="10 pages"):
        pdf_import.parse_contract_note(make_contract_note(pages=11))


@pytest.mark.parametrize("password", ["fictional-test-password", ""])
def test_encrypted_pdf_rejected_even_with_empty_password(password):
    with pytest.raises(ValueError, match="Encrypted PDFs"):
        pdf_import.parse_contract_note(make_contract_note(password=password))


def test_image_only_pdf_rejected():
    with pytest.raises(ValueError, match="Image-only"):
        pdf_import.parse_contract_note(make_contract_note(image_only=True))


@pytest.mark.parametrize("payload", [b"%PDF-1.4\nbroken", b"%PDF-1.4\n%%EOF"])
def test_malformed_pdf_rejected(payload):
    with pytest.raises(ValueError, match="Malformed PDF"):
        pdf_import.parse_contract_note(payload)


def test_extracted_text_limit_counts_utf8_across_pages():
    document = Mock()
    document.doc.encryption = None
    first, second = Mock(), Mock()
    first.extract_text.return_value = "a" * (pdf_import.MAX_TEXT_BYTES - 1)
    second.extract_text.return_value = "é"
    document.pages = [first, second]
    with patch.object(pdf_import.pdfplumber, "open") as opened:
        opened.return_value.__enter__.return_value = document
        with pytest.raises(ValueError, match="200 KB"):
            pdf_import.parse_contract_note(b"%PDF-test")
        first.extract_text.return_value = "a" * pdf_import.MAX_TEXT_BYTES
        document.pages = [first]
        # At the exact limit, size validation passes and layout validation runs.
        with pytest.raises(ValueError, match="Unsupported PDF layout"):
            pdf_import.parse_contract_note(b"%PDF-test")


@pytest.mark.parametrize("label, value, error", [
    ("Contract number", "bad value", "Contract number"),
    ("Stock name", "x" * 161, "Stock name"),
    ("Trade date", "2026-02-30", "real calendar"),
    ("Trade date", "20261102", "YYYY-MM-DD"),
    ("Settlement date", "2026-11-01", "precede"),
    ("Stock code", "../invalid", "Stock code"),
    ("Side", "hold", "Side"),
    ("Quantity", "0", "Quantity"),
    ("Quantity", "1.5", "Quantity"),
    ("Price (RM)", "0", "Price"),
    ("Price (RM)", "1.00001", "Price"),
    ("Price (RM)", "NaN", "Price"),
    ("Brokerage (RM)", "-1", "Brokerage"),
    ("Clearing fee (RM)", "Infinity", "Clearing"),
    ("Stamp duty (RM)", "0.001", "Stamp"),
    ("Net amount (RM)", "NaN", "Net amount"),
])
def test_invalid_note_fields_rejected(label, value, error):
    with pytest.raises(ValueError, match=error):
        pdf_import.parse_contract_note(make_contract_note(**{label: value}))


def test_unknown_or_missing_layout_fields_rejected():
    with pytest.raises(ValueError, match="Malformed synthetic"):
        pdf_import.parse_contract_note(make_contract_note(**{"Extra field": "unexpected"}))
    with patch.object(pdf_import, "_extract_text", return_value="Other layout"):
        with pytest.raises(ValueError, match="Unsupported PDF layout"):
            pdf_import.parse_contract_note(b"%PDF-test")
    text = f"{pdf_import.TITLE}\n{pdf_import.DISCLAIMER}\nContract number: SYN-1"
    with patch.object(pdf_import, "_extract_text", return_value=text):
        with pytest.raises(ValueError, match="missing required fields"):
            pdf_import.parse_contract_note(b"%PDF-test")
    text += "\nContract number: SYN-2"
    with patch.object(pdf_import, "_extract_text", return_value=text):
        with pytest.raises(ValueError, match="Malformed synthetic"):
            pdf_import.parse_contract_note(b"%PDF-test")


def test_parser_requires_bytes():
    with pytest.raises(TypeError, match="expects bytes"):
        pdf_import.parse_contract_note("%PDF-test")


def upload_note(client, portfolio_id, contents=None):
    return client.post(
        f"/portfolios/{portfolio_id}/import",
        data={"format": "pdf", "file": (BytesIO(
            make_contract_note() if contents is None else contents,
        ), "synthetic-note.pdf")},
        content_type="multipart/form-data",
    )


@pytest.fixture
def unit_route_client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("DB_NAME", "tradebook_test")
    with patch("sources.indexes.ensure_all_indexes"):
        application = importlib.import_module("tradebook")
    for key, value in {"TESTING": True, "LOGIN_DISABLED": True, "WTF_CSRF_ENABLED": False}.items():
        monkeypatch.setitem(application.app.config, key, value)
    monkeypatch.setattr(application.limiter, "enabled", False)
    user_id, portfolio_id = ObjectId(), ObjectId()
    monkeypatch.setattr(application, "current_user", Mock(get_id=lambda: str(user_id)))
    database = Mock()
    database.portfolios.find_one.return_value = {
        "_id": portfolio_id, "user_id": user_id, "name": "Synthetic book",
        "currency": "MYR", "version": 1,
    }
    database.portfolios.update_one.return_value.matched_count = 1
    database.trades.find.return_value.sort.return_value = []
    database.import_previews.insert_one.return_value.inserted_id = ObjectId()
    database.import_previews.update_one.return_value.modified_count = 1
    monkeypatch.setattr(application, "db", database)
    with application.app.test_client() as client:
        yield client, database, portfolio_id


def test_unit_route_upload_creates_pdf_preview_without_spooling_or_cookie_rows(unit_route_client):
    client, database, portfolio_id = unit_route_client
    contents = make_contract_note(**{"Stock name": "x" * 160})
    with patch(
        "werkzeug.formparser.SpooledTemporaryFile", side_effect=AssertionError("disk spool"),
    ):
        response = upload_note(client, portfolio_id, contents)
        # Exercise the large-upload path as well, rejected on PDF magic after parsing multipart.
        large = upload_note(client, portfolio_id, b"x" * (600 * 1024))
    assert response.status_code == 200
    assert large.status_code == 400
    document = database.import_previews.insert_one.call_args.args[0]
    assert document["source"] == "pdf"
    assert document["requires_acknowledgement"] is False
    assert from_d128(document["rows"][0]["fees"]) == Decimal("9.94")
    assert b"Net amount reconciles within RM0.01" in response.data
    assert b'name="rows"' not in response.data
    database.trades.insert_many.assert_not_called()
    with client.session_transaction() as session:
        assert "rows" not in session
        assert "pdf" not in session


def test_unit_route_mismatch_blocks_without_checkbox_then_confirms(unit_route_client):
    client, database, portfolio_id = unit_route_client
    response = upload_note(client, portfolio_id, make_contract_note(**{"Net amount (RM)": "1.00"}))
    assert response.status_code == 200
    assert b"Reconciliation mismatch" in response.data
    assert b'name="acknowledge_mismatch" required' in response.data
    preview = database.import_previews.insert_one.call_args.args[0]
    assert preview["requires_acknowledgement"] is True
    preview["_id"] = database.import_previews.insert_one.return_value.inserted_id
    database.import_previews.find_one.return_value = preview
    path = f"/imports/{preview['_id']}/confirm"
    assert client.post(path).status_code == 400
    database.import_previews.update_one.assert_not_called()
    database.portfolios.update_one.assert_not_called()
    database.trades.insert_many.assert_not_called()
    assert client.post(path, data={"acknowledge_mismatch": "on"}).status_code == 302
    assert database.import_previews.update_one.call_args_list[0].args[1]["$set"] == {
        "status": "confirming", "mismatch_acknowledged": True,
    }
    database.trades.insert_many.assert_called_once()


@pytest.mark.parametrize("contents, status", [
    (b"not a PDF", 400), (b"x" * (pdf_import.MAX_BYTES + 1), 413),
    (make_contract_note(pages=11), 400), (make_contract_note(password="fictional"), 400),
])
def test_unit_route_rejects_invalid_uploads_without_preview(unit_route_client, contents, status):
    client, database, portfolio_id = unit_route_client
    assert upload_note(client, portfolio_id, contents).status_code == status
    database.import_previews.insert_one.assert_not_called()


def test_unit_route_upload_checks_portfolio_ownership_and_currency(unit_route_client):
    client, database, portfolio_id = unit_route_client
    database.portfolios.find_one.return_value["currency"] = "USD"
    assert upload_note(client, portfolio_id).status_code == 400
    database.import_previews.insert_one.assert_not_called()
    database.portfolios.find_one.return_value = None
    assert upload_note(client, portfolio_id).status_code == 404
    database.import_previews.insert_one.assert_not_called()


def test_unit_route_upload_and_confirmation_require_csrf(unit_route_client, monkeypatch):
    client, database, portfolio_id = unit_route_client
    application = importlib.import_module("tradebook")
    monkeypatch.setitem(application.app.config, "WTF_CSRF_ENABLED", True)
    assert upload_note(client, portfolio_id).status_code == 400
    assert client.post(f"/imports/{ObjectId()}/confirm").status_code == 400
    database.import_previews.insert_one.assert_not_called()
    database.import_previews.find_one.assert_not_called()


def test_route_pdf_preview_and_confirm_real_mongo(logged_in_client, db):
    user_id = db.users.find_one({"email": "user@example.com"})["_id"]
    portfolio_id = portfolios.create_portfolio(db, user_id, "PDF book")
    response = upload_note(logged_in_client, portfolio_id)
    assert response.status_code == 200
    preview = db.import_previews.find_one({"portfolio_id": portfolio_id})
    assert preview["source"] == "pdf"
    assert preview["requires_acknowledgement"] is False
    assert db.trades.count_documents({}) == 0
    for _ in range(2):
        assert logged_in_client.post(f"/imports/{preview['_id']}/confirm").status_code == 302
    documents = trades.list_trades(db, portfolio_id)
    assert len(documents) == 1
    assert documents[0]["source"] == "pdf"
    assert from_d128(documents[0]["fees"]) == Decimal("9.94")


def test_route_pdf_mismatch_rejects_then_records_acknowledgement(logged_in_client, db):
    user_id = db.users.find_one({"email": "user@example.com"})["_id"]
    portfolio_id = portfolios.create_portfolio(db, user_id, "Mismatch book")
    assert upload_note(logged_in_client, portfolio_id, make_contract_note(**{
        "Net amount (RM)": "0.01",
    })).status_code == 200
    preview = db.import_previews.find_one({"portfolio_id": portfolio_id})
    path = f"/imports/{preview['_id']}/confirm"
    assert logged_in_client.post(path).status_code == 400
    assert db.trades.count_documents({}) == 0
    assert db.import_previews.find_one({"_id": preview["_id"]})["status"] == "pending"
    assert logged_in_client.post(path, data={"acknowledge_mismatch": "on"}).status_code == 302
    assert db.import_previews.find_one({"_id": preview["_id"]})["mismatch_acknowledged"] is True
    assert db.trades.count_documents({"import_id": preview["_id"]}) == 1


def test_route_sell_note_replays_existing_history(logged_in_client, db):
    user_id = db.users.find_one({"email": "user@example.com"})["_id"]
    portfolio_id = portfolios.create_portfolio(db, user_id, "Sell book")
    trades.add_trade(db, user_id, portfolio_id, "DEMO1", "buy", 100, "9", "1", "2026-11-01", 1)
    response = upload_note(logged_in_client, portfolio_id, make_contract_note(side="sell"))
    assert response.status_code == 200
    preview = db.import_previews.find_one({"portfolio_id": portfolio_id})
    assert logged_in_client.post(f"/imports/{preview['_id']}/confirm").status_code == 302
    assert db.trades.count_documents({"portfolio_id": portfolio_id}) == 2


def test_route_other_user_cannot_upload_or_acknowledge(logged_in_client, db):
    owner_id = ObjectId()
    portfolio_id = portfolios.create_portfolio(db, owner_id, "Private PDF book")
    rows, _ = pdf_import.parse_contract_note(make_contract_note())
    preview_id = imports.create_preview(
        db, owner_id, portfolio_id, rows, "pdf", requires_acknowledgement=True,
    )
    assert upload_note(logged_in_client, portfolio_id).status_code == 404
    assert logged_in_client.post(
        f"/imports/{preview_id}/confirm", data={"acknowledge_mismatch": "on"},
    ).status_code == 404
    assert db.trades.count_documents({}) == 0
