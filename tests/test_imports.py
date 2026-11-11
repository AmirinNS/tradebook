"""Import confirmation checks against Mongo and isolated failure boundaries."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest
from bson.objectid import ObjectId
from pymongo.collection import Collection
from pymongo.errors import AutoReconnect

from modules import imports, portfolios, trades
from modules.csv_import import parse_trades_csv
from sources.functions import utcnow
from sources.money import from_d128

CSV = "date,symbol,side,qty,price,fees\n2026-11-02,DEMO1,buy,10,10,1\n"


def setup_preview(db, text=CSV):
    user_id = ObjectId()
    portfolio_id = portfolios.create_portfolio(db, user_id, "Import book")
    rows, errors = parse_trades_csv(text)
    assert not errors
    preview_id = imports.create_preview(db, user_id, portfolio_id, rows, "csv")
    return user_id, portfolio_id, preview_id


def test_confirm_persists_money_and_double_confirm_inserts_once(db):
    user_id, portfolio_id, preview_id = setup_preview(db)
    for _ in range(2):
        result = imports.confirm_preview(db, str(user_id), str(preview_id))
        assert result["status"] == "confirmed"
    rows = trades.list_trades(db, portfolio_id)
    assert len(rows) == 1
    assert from_d128(rows[0]["price"]) == Decimal("10.0000")
    assert from_d128(rows[0]["fees"]) == Decimal("1.00")
    assert rows[0]["import_id"] == preview_id
    assert rows[0]["source"] == "csv"
    assert portfolios.get_portfolio(db, portfolio_id)["version"] == 2


def test_preview_ownership_and_expiry(db):
    user_id, _, preview_id = setup_preview(db)
    with pytest.raises(imports.PreviewNotFoundError):
        imports.confirm_preview(db, ObjectId(), preview_id)
    db.import_previews.update_one(
        {"_id": preview_id}, {"$set": {"created_at": utcnow() - timedelta(hours=2)}},
    )
    with pytest.raises(imports.PreviewNotFoundError):
        imports.confirm_preview(db, user_id, preview_id)
    assert db.trades.count_documents({}) == 0


def test_invalid_current_history_leaves_existing_trades_unchanged(db):
    user_id, portfolio_id, _ = setup_preview(db)
    trades.add_trade(db, user_id, portfolio_id, "DEMO1", "buy", 10, "10", "0", "2026-11-01", 1)
    rows, _ = parse_trades_csv(CSV.replace("buy,10", "sell,10"))
    preview_id = imports.create_preview(db, user_id, portfolio_id, rows, "csv")
    trades.add_trade(db, user_id, portfolio_id, "DEMO1", "sell", 10, "12", "0", "2026-11-02", 2)
    before = trades.list_trades(db, portfolio_id)
    with pytest.raises(ValueError, match="Sell exceeds open quantity"):
        imports.confirm_preview(db, user_id, preview_id)
    assert trades.list_trades(db, portfolio_id) == before
    assert db.import_previews.find_one({"_id": preview_id})["status"] == "failed"


def test_currency_is_rechecked_at_confirmation(db):
    user_id, portfolio_id, preview_id = setup_preview(db)
    db.portfolios.update_one({"_id": portfolio_id}, {"$set": {"currency": "USD"}})
    with pytest.raises(ValueError, match="currency"):
        imports.confirm_preview(db, user_id, preview_id)
    assert db.trades.count_documents({}) == 0


def test_same_day_sequences_follow_existing_and_preserve_file_order(db):
    user_id, portfolio_id, _ = setup_preview(db)
    trades.add_trade(db, user_id, portfolio_id, "DEMO1", "buy", 5, "10", "0", "2026-11-02", 1)
    rows, _ = parse_trades_csv(CSV + "2026-11-02,DEMO1,sell,15,12,1\n")
    preview_id = imports.create_preview(db, user_id, portfolio_id, rows, "csv")
    imports.confirm_preview(db, user_id, preview_id)
    rows = trades.list_trades(db, portfolio_id)
    assert [row["seq"] for row in rows] == [0, 1, 2]
    assert [row["side"] for row in rows] == ["buy", "buy", "sell"]


def test_partial_insert_is_rolled_back_without_deleting_other_trades(db, monkeypatch):
    user_id, portfolio_id, preview_id = setup_preview(db, CSV + "2026-11-03,DEMO2,buy,2,5,0\n")
    trades.add_trade(db, user_id, portfolio_id, "DEMO3", "buy", 1, "1", "0", "2026-11-01", 1)
    original = Collection.insert_many

    def partial_insert(collection, documents, *args, **kwargs):
        original(collection, documents[:1], *args, **kwargs)
        raise AutoReconnect("Simulated partial insert failure")

    monkeypatch.setattr(Collection, "insert_many", partial_insert)
    with pytest.raises(AutoReconnect):
        imports.confirm_preview(db, user_id, preview_id)
    assert db.trades.count_documents({"import_id": preview_id}) == 0
    assert db.trades.count_documents({"portfolio_id": portfolio_id, "symbol": "DEMO3"}) == 1
    assert db.import_previews.find_one({"_id": preview_id})["status"] == "failed"
    imports.confirm_preview(db, user_id, preview_id)
    assert db.trades.count_documents({"portfolio_id": portfolio_id}) == 1


def test_preview_ttl_index(db):
    assert any(
        index.get("expireAfterSeconds") == 3600
        and list(index["key"].items()) == [("created_at", 1)]
        for index in db.import_previews.list_indexes()
    )


@pytest.fixture
def unit_preview():
    database = Mock()
    user_id, portfolio_id, preview_id = ObjectId(), ObjectId(), ObjectId()
    row = parse_trades_csv(CSV)[0][0]
    trade = imports.Trade(portfolio_id=portfolio_id, seq=0, **row)
    preview = {
        "_id": preview_id, "portfolio_id": portfolio_id, "user_id": user_id,
        "status": "pending", "rows": [trades._trade_to_doc(trade)],
    }
    database.import_previews.find_one.return_value = preview
    database.import_previews.update_one.return_value = Mock(modified_count=1)
    database.portfolios.find_one.return_value = {
        "_id": portfolio_id, "user_id": user_id, "version": 4, "currency": "MYR",
    }
    database.portfolios.update_one.return_value = Mock(matched_count=1)
    database.trades.find.return_value.sort.return_value = []
    return database, user_id, preview_id, trade


def test_unit_confirmation_replays_assigns_sequence_and_serializes(unit_preview):
    database, user_id, preview_id, trade = unit_preview
    existing = replace(trade, seq=7, date=datetime(2026, 11, 2, tzinfo=timezone.utc))
    database.trades.find.return_value.sort.return_value = [trades._trade_to_doc(existing)]
    result = imports.confirm_preview(database, user_id, preview_id)
    assert result["status"] == "confirmed"
    document = database.trades.insert_many.call_args.args[0][0]
    assert document["seq"] == 8
    assert document["import_id"] == preview_id
    database.portfolios.update_one.assert_called_once_with(
        {"_id": trade.portfolio_id, "user_id": user_id, "version": 4},
        {"$inc": {"version": 1}},
    )


def test_unit_double_submit_does_not_claim_or_insert(unit_preview):
    database, user_id, preview_id, _ = unit_preview
    database.import_previews.update_one.return_value.modified_count = 0
    imports.confirm_preview(database, user_id, preview_id)
    database.portfolios.update_one.assert_not_called()
    database.trades.insert_many.assert_not_called()


def test_unit_invalid_history_never_inserts(unit_preview):
    database, user_id, preview_id, _ = unit_preview
    database.import_previews.find_one.return_value["rows"][0]["side"] = "sell"
    with pytest.raises(ValueError, match="Sell exceeds open quantity"):
        imports.confirm_preview(database, user_id, preview_id)
    database.trades.insert_many.assert_not_called()
    assert database.import_previews.update_one.call_args.args[1] == {"$set": {"status": "failed"}}


def test_unit_currency_recheck_never_inserts(unit_preview):
    database, user_id, preview_id, _ = unit_preview
    database.portfolios.find_one.return_value["currency"] = "USD"
    with pytest.raises(ValueError, match="currency"):
        imports.confirm_preview(database, user_id, preview_id)
    database.trades.insert_many.assert_not_called()


def test_unit_missing_preview_does_not_claim_or_insert(unit_preview):
    database, user_id, preview_id, _ = unit_preview
    database.import_previews.find_one.return_value = None
    with pytest.raises(imports.PreviewNotFoundError):
        imports.confirm_preview(database, user_id, preview_id)
    query = database.import_previews.find_one.call_args.args[0]
    assert query["user_id"] == user_id
    assert query["created_at"]["$gt"].tzinfo is not None
    database.portfolios.update_one.assert_not_called()
    database.trades.insert_many.assert_not_called()


def test_unit_insert_failure_cleans_only_this_import(unit_preview):
    database, user_id, preview_id, trade = unit_preview
    database.trades.insert_many.side_effect = AutoReconnect("Simulated insert failure")
    with pytest.raises(AutoReconnect):
        imports.confirm_preview(database, user_id, preview_id)
    database.trades.delete_many.assert_called_once_with(
        {"portfolio_id": trade.portfolio_id, "import_id": preview_id},
    )
    assert database.import_previews.update_one.call_args.args[1] == {"$set": {"status": "failed"}}


def test_unit_version_conflict_never_inserts(unit_preview):
    database, user_id, preview_id, _ = unit_preview
    database.portfolios.update_one.return_value.matched_count = 0
    with pytest.raises(portfolios.StaleVersionError):
        imports.confirm_preview(database, user_id, preview_id)
    database.trades.insert_many.assert_not_called()


def test_unit_acknowledgement_required_before_any_write(unit_preview):
    database, user_id, preview_id, _ = unit_preview
    database.import_previews.find_one.return_value["requires_acknowledgement"] = True
    with pytest.raises(ValueError, match="Acknowledge.*mismatch"):
        imports.confirm_preview(database, user_id, preview_id)
    database.import_previews.update_one.assert_not_called()
    database.portfolios.update_one.assert_not_called()
    database.trades.insert_many.assert_not_called()


def test_unit_acknowledged_mismatch_is_recorded_in_atomic_claim(unit_preview):
    database, user_id, preview_id, _ = unit_preview
    database.import_previews.find_one.return_value["requires_acknowledgement"] = True
    result = imports.confirm_preview(database, user_id, preview_id, acknowledge_mismatch=True)
    assert result["status"] == "confirmed"
    claim = database.import_previews.update_one.call_args_list[0]
    assert claim.args[0]["status"] == "pending"
    assert claim.args[1] == {"$set": {"status": "confirming", "mismatch_acknowledged": True}}
    database.trades.insert_many.assert_called_once()


def test_unit_csv_confirmation_needs_no_acknowledgement(unit_preview):
    database, user_id, preview_id, _ = unit_preview
    assert imports.confirm_preview(database, user_id, preview_id)["status"] == "confirmed"
    assert database.import_previews.update_one.call_args_list[0].args[1] == {
        "$set": {"status": "confirming"},
    }


def test_unit_pdf_currency_is_rechecked_before_claim(unit_preview):
    database, user_id, preview_id, _ = unit_preview
    database.import_previews.find_one.return_value["source"] = "pdf"
    database.portfolios.find_one.return_value["currency"] = "USD"
    with pytest.raises(ValueError, match="MYR"):
        imports.confirm_preview(database, user_id, preview_id, acknowledge_mismatch=True)
    database.import_previews.update_one.assert_not_called()
    database.portfolios.update_one.assert_not_called()
    database.trades.insert_many.assert_not_called()


def test_mismatch_requires_acknowledgement_and_preserves_pending_preview(db):
    user_id, portfolio_id, _ = setup_preview(db)
    rows, _ = parse_trades_csv(CSV)
    preview_id = imports.create_preview(
        db, user_id, portfolio_id, rows, "pdf", requires_acknowledgement=True,
    )
    version = portfolios.get_portfolio(db, portfolio_id)["version"]
    with pytest.raises(ValueError, match="Acknowledge.*mismatch"):
        imports.confirm_preview(db, user_id, preview_id)
    assert db.trades.count_documents({}) == 0
    assert portfolios.get_portfolio(db, portfolio_id)["version"] == version
    preview = db.import_previews.find_one({"_id": preview_id})
    assert preview["status"] == "pending"
    assert preview["requires_acknowledgement"] is True
    assert "mismatch_acknowledged" not in preview
    imports.confirm_preview(db, user_id, preview_id, acknowledge_mismatch=True)
    preview = db.import_previews.find_one({"_id": preview_id})
    assert preview["status"] == "confirmed"
    assert preview["mismatch_acknowledged"] is True
    imports.confirm_preview(db, user_id, preview_id)
    assert db.trades.count_documents({"import_id": preview_id}) == 1


def test_csv_preview_default_requires_no_acknowledgement(db):
    user_id, _, preview_id = setup_preview(db)
    preview = db.import_previews.find_one({"_id": preview_id})
    assert preview["requires_acknowledgement"] is False
    assert imports.confirm_preview(db, user_id, preview_id)["status"] == "confirmed"
