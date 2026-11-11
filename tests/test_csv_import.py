from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from modules.csv_import import MAX_BYTES, MAX_ROWS, parse_trades_csv
from modules.ledger import Trade, validate_trade
from modules.pnl import fifo_positions

FIXTURE = Path(__file__).parent / "fixtures" / "sample_trades.csv"
HEADER = "date,symbol,side,qty,price,fees"
ROW = "2026-01-05,DEMO1,buy,100,1.2500,8.00"
EXPECTED_ROW = {
    "symbol": "DEMO1",
    "side": "buy",
    "qty": 100,
    "price": Decimal("1.2500"),
    "fees": Decimal("8.00"),
    "date": datetime(2026, 1, 5, tzinfo=timezone.utc),
    "source": "csv",
}


def text(*lines):
    return "\n".join((HEADER, *lines)) + "\n"


def test_sample_file_parses_every_row_into_the_ledger_trade_shape():
    rows, errors = parse_trades_csv(FIXTURE.read_text(encoding="utf-8"))
    assert errors == []
    assert len(rows) == 12
    assert rows[0] == EXPECTED_ROW
    assert set(rows[3]) == set(EXPECTED_ROW)


def test_sample_rows_are_valid_trades_and_replay_as_fifo_history():
    rows, errors = parse_trades_csv(FIXTURE.read_text(encoding="utf-8"))
    assert errors == []
    trades = [
        validate_trade(
            Trade(
                "portfolio",
                row["symbol"],
                row["side"],
                row["qty"],
                row["price"],
                row["fees"],
                row["date"],
                seq,
                "csv",
            ),
            "MYR",
        )
        for seq, row in enumerate(rows)
    ]
    lots, realized = fifo_positions(trades)
    remaining = {}
    for lot in lots:
        remaining[lot["symbol"]] = remaining.get(lot["symbol"], 0) + lot["qty"]
    assert remaining == {
        "DEMO1": 160,
        "DEMO2": 100,
        "DEMO3": 100,
        "DEMO4": 300,
        "DEMO5": 600,
    }
    assert len(realized) == 5


def test_bad_date_is_rejected_with_its_line_number():
    rows, errors = parse_trades_csv(text("2026-13-01,DEMO1,buy,100,1.2500,8.00"))
    assert rows == []
    assert errors == ["Line 2: date is not a real calendar date."]


@pytest.mark.parametrize(
    "day", ["05/01/2026", "2026-1-5", "20260105", "", "2026-01-05T00:00:00"]
)
def test_date_must_be_a_plain_iso_date(day):
    rows, errors = parse_trades_csv(text(f"{day},DEMO1,buy,100,1.2500,8.00"))
    assert rows == []
    assert errors == ["Line 2: date must be an ISO date, YYYY-MM-DD."]


@pytest.mark.parametrize("qty", ["-5", "0", "1.5", "1e2", "abc", ""])
def test_quantity_must_be_a_positive_whole_number(qty):
    rows, errors = parse_trades_csv(text(f"2026-01-05,DEMO1,buy,{qty},1.2500,8.00"))
    assert rows == []
    assert errors == ["Line 2: qty must be a positive whole number of shares."]


@pytest.mark.parametrize("side", ["hold", "long", "", "selll"])
def test_side_must_be_buy_or_sell(side):
    rows, errors = parse_trades_csv(text(f"2026-01-05,DEMO1,{side},100,1.2500,8.00"))
    assert rows == []
    assert errors == ["Line 2: side must be buy or sell."]


def test_side_is_case_insensitive_and_normalized():
    rows, errors = parse_trades_csv(text("2026-01-05,DEMO1,SELL,100,1.2500,8.00"))
    assert errors == []
    assert rows[0]["side"] == "sell"


@pytest.mark.parametrize("symbol", ["DEMO 1", "DEMO_1", ""])
def test_symbol_must_be_a_ticker(symbol):
    rows, errors = parse_trades_csv(text(f"2026-01-05,{symbol},buy,100,1.2500,8.00"))
    assert rows == []
    assert errors == ["Line 2: symbol must be a ticker (letters, digits, dot or dash)."]


@pytest.mark.parametrize(("raw", "expected"), [("demo1", "DEMO1"), ("demo1.KL", "DEMO1.KL")])
def test_lowercase_symbols_are_uppercased(raw, expected):
    rows, errors = parse_trades_csv(text(f"2026-01-05,{raw},BUY,100,1.2500,8.00"))
    assert errors == []
    assert rows[0]["symbol"] == expected
    assert rows[0]["side"] == "buy"


def test_a_free_text_ticker_outside_the_universe_is_accepted():
    rows, errors = parse_trades_csv(text("2026-01-05,ABC-1.KL,buy,100,1.2500,8.00"))
    assert errors == []
    assert rows[0]["symbol"] == "ABC-1.KL"


@pytest.mark.parametrize("value", ["0", "-1.2500", "1.23456"])
def test_price_must_be_positive_with_at_most_four_places(value):
    rows, errors = parse_trades_csv(text(f"2026-01-05,DEMO1,buy,100,{value},8.00"))
    assert rows == []
    assert errors == ["Line 2: price must be positive with at most 4 decimal places."]


@pytest.mark.parametrize("value", ["abc", "", "nan", "inf"])
def test_price_must_be_a_number(value):
    rows, errors = parse_trades_csv(text(f"2026-01-05,DEMO1,buy,100,{value},8.00"))
    assert rows == []
    assert errors == ["Line 2: price and fees must be numbers."]


@pytest.mark.parametrize("value", ["-1", "1.005"])
def test_fees_cannot_be_negative_and_allow_two_places(value):
    rows, errors = parse_trades_csv(text(f"2026-01-05,DEMO1,buy,100,1.2500,{value}"))
    assert rows == []
    assert errors == ["Line 2: fees cannot be negative and allow at most 2 decimal places."]


@pytest.mark.parametrize("value", ["abc", "", "nan", "inf"])
def test_fees_must_be_a_number(value):
    rows, errors = parse_trades_csv(text(f"2026-01-05,DEMO1,buy,100,1.2500,{value}"))
    assert rows == []
    assert errors == ["Line 2: price and fees must be numbers."]


def test_price_and_fees_are_rounded_to_the_ledger_precision():
    rows, errors = parse_trades_csv(text("2026-01-05,DEMO1,buy,100,1.5,0"))
    assert errors == []
    assert rows[0]["price"] == Decimal("1.5000")
    assert rows[0]["fees"] == Decimal("0.00")


def test_surrounding_whitespace_in_cells_is_ignored():
    rows, errors = parse_trades_csv(text(" 2026-01-05 , DEMO1 , buy , 100 , 1.2500 , 8.00 "))
    assert errors == []
    assert rows[0] == EXPECTED_ROW


def test_a_row_with_the_wrong_column_count_reports_its_line():
    rows, errors = parse_trades_csv(text(ROW, "2026-01-06,DEMO1,sell,10,1.5"))
    assert rows == [EXPECTED_ROW]
    assert errors == ["Line 3: expected 6 columns, got 5."]


def test_bad_rows_keep_their_line_number_and_valid_rows_survive():
    body = f"{ROW}\n2026-01-06,DEMO1,hold,10,1.5000,0.00\n2026-01-07,DEMO2,buy,5,2,1\n"
    rows, errors = parse_trades_csv(f"{HEADER}\n{body}")
    assert [row["symbol"] for row in rows] == ["DEMO1", "DEMO2"]
    assert errors == ["Line 3: side must be buy or sell."]


def test_too_many_rows_rejects_the_whole_file():
    body = "".join("2026-01-05,DEMO1,buy,1,1.0000,0.00\n" for _ in range(MAX_ROWS + 1))
    rows, errors = parse_trades_csv(f"{HEADER}\n{body}")
    assert rows == []
    assert errors == [f"File has {MAX_ROWS + 1} rows; the limit is {MAX_ROWS}."]


def test_a_file_over_the_size_limit_rejects_the_whole_file():
    rows, errors = parse_trades_csv("x" * (MAX_BYTES + 1))
    assert rows == []
    assert errors == ["File is larger than the 1024 KB limit."]


@pytest.mark.parametrize("content", ["", "   ", "\n\n", "\ufeff"])
def test_an_empty_file_is_reported(content):
    rows, errors = parse_trades_csv(content)
    assert rows == []
    assert errors == ["File is empty."]


def test_byte_order_mark_and_windows_line_endings_are_handled():
    body = "\r\n".join((HEADER, ROW, "2026-01-06,DEMO2,sell,5,2.0000,1.00", ""))
    rows, errors = parse_trades_csv("\ufeff" + body)
    assert errors == []
    assert [row["symbol"] for row in rows] == ["DEMO1", "DEMO2"]
    assert rows[1] == {
        "symbol": "DEMO2",
        "side": "sell",
        "qty": 5,
        "price": Decimal("2.0000"),
        "fees": Decimal("1.00"),
        "date": datetime(2026, 1, 6, tzinfo=timezone.utc),
        "source": "csv",
    }


def test_blank_lines_are_skipped_without_shifting_line_numbers():
    rows, errors = parse_trades_csv(f"{HEADER}\n\n{ROW}\n\n\n2026-01-06,DEMO1,hold,1,1,0\n")
    assert [row["symbol"] for row in rows] == ["DEMO1"]
    assert errors == ["Line 6: side must be buy or sell."]


@pytest.mark.parametrize(
    "header",
    [
        "date,symbol,side,qty,price",
        "date,symbol,side,qty,price,fees,notes",
        "",
    ],
)
def test_a_wrong_header_rejects_the_whole_file(header):
    rows, errors = parse_trades_csv(f"{header}\n{ROW}\n")
    assert rows == []
    assert errors == ["Header must be date,symbol,side,qty,price,fees."]


def test_header_matching_ignores_case_and_whitespace():
    rows, errors = parse_trades_csv(f" date , symbol , side , qty , price , fees \n{ROW}\n")
    assert errors == []
    assert rows == [EXPECTED_ROW]


def test_bytes_are_rejected_at_the_boundary():
    with pytest.raises(TypeError):
        parse_trades_csv(ROW.encode("utf-8"))
