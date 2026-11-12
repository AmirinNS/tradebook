"""Landing page routes, market states and account-aware calls to action."""

from datetime import date
from decimal import Decimal
from html.parser import HTMLParser

import pytest

from modules import lessons, prices
from sources import universe


class Links(HTMLParser):
    """Collect link labels and destinations from the rendered document."""

    def __init__(self):
        super().__init__()
        self.links = []
        self.href = None
        self.label = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.label = []

    def handle_data(self, data):
        if self.href is not None:
            self.label.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.href is not None:
            self.links.append((" ".join("".join(self.label).split()), self.href))
            self.href = None


def test_landing_anonymous_calls_to_action(client):
    response = client.get("/")
    assert response.status_code == 200
    links = Links()
    links.feed(response.text)
    assert ("View live demo", "/demo") in links.links
    assert ("Create an account", "/register") in links.links
    assert "Open your journal" not in response.text
    assert f"{len(lessons.list_lessons())} lessons" in response.text
    assert f'<span class="tb-num tb-metric">{len(universe.get_universe())}</span>' in response.text


def test_landing_authenticated_calls_to_action(logged_in_client):
    response = logged_in_client.get("/")
    assert response.status_code == 200
    links = Links()
    links.feed(response.text)
    assert ("Open your journal", "/portfolios") in links.links
    assert ("View live demo", "/demo") in links.links
    assert ("Create an account", "/register") not in links.links


@pytest.mark.parametrize(
    ("previous", "latest", "display", "direction"),
    [
        ("9.0000", "10.1250", "+1.1250", "gain"),
        ("11.0000", "10.1250", "-0.8750", "loss"),
        ("10.1250", "10.1250", "0.00", None),
        (None, "10.1250", "Day change unavailable", None),
    ],
)
def test_landing_real_symbol_prices(client, db, previous, latest, display, direction):
    symbol = "1155.KL"
    bars = []
    for day, close in ((1, previous), (2, latest)):
        if close is not None:
            bars.append({
                "symbol": symbol, "date": date(2026, 11, day),
                "open": Decimal(close), "high": Decimal(close),
                "low": Decimal(close), "close": Decimal(close), "volume": 100,
            })
    prices.upsert_bars(db, bars)
    response = client.get("/")
    assert response.status_code == 200
    quote = response.text.split('class="tb-landing-quote"', 1)[1].split("</li>", 1)[0]
    assert symbol in quote
    assert 'href="/stocks/1155.KL"' in quote
    assert "10.1250" in quote
    assert "2026-11-02" in quote
    assert display in quote
    if direction:
        assert f'visually-hidden">{direction}</span>' in quote
        assert ("▲" if direction == "gain" else "▼") in quote
    else:
        assert "▲" not in quote and "▼" not in quote
    assert "MYR · Latest stored daily closes" in response.text


def test_landing_hides_unpriced_symbols(client):
    response = client.get("/")
    assert 'class="tb-landing-quote"' not in response.text
    assert "No stored prices yet." in response.text
    assert 'role="region" aria-label="MYR market prices, scroll for more symbols"' in response.text


def test_landing_synthetic_label(client, db):
    prices.upsert_bars(db, [{
        "symbol": "DEMO1", "date": date(2026, 11, 2),
        "open": Decimal("5"), "high": Decimal("5"),
        "low": Decimal("5"), "close": Decimal("5"), "volume": 100,
    }])
    response = client.get("/")
    quotes = response.text.split('class="tb-landing-quote"')[1:]
    assert len(quotes) == 1
    assert "/stocks/DEMO1" in quotes[0]
    assert "Synthetic demo data" in quotes[0]
