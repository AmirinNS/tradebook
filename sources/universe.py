"""Stock universe definitions: Bursa Malaysia (.KL), US large caps, and DEMO symbols."""

UNIVERSE = {
    # Bursa Malaysia (.KL) — currency MYR, exchange BURSA
    "1155.KL": {
        "symbol": "1155.KL",
        "name": "Malayan Banking Berhad",
        "sector": "Financial Services",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "1295.KL": {
        "symbol": "1295.KL",
        "name": "Public Bank Berhad",
        "sector": "Financial Services",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "1023.KL": {
        "symbol": "1023.KL",
        "name": "CIMB Group Holdings Berhad",
        "sector": "Financial Services",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "5347.KL": {
        "symbol": "5347.KL",
        "name": "Tenaga Nasional Berhad",
        "sector": "Utilities",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "5183.KL": {
        "symbol": "5183.KL",
        "name": "PETRONAS Chemicals Group Berhad",
        "sector": "Basic Materials",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "6033.KL": {
        "symbol": "6033.KL",
        "name": "PETRONAS Gas Berhad",
        "sector": "Utilities",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "5681.KL": {
        "symbol": "5681.KL",
        "name": "PETRONAS Dagangan Berhad",
        "sector": "Energy",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "5225.KL": {
        "symbol": "5225.KL",
        "name": "IHH Healthcare Berhad",
        "sector": "Healthcare",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "6888.KL": {
        "symbol": "6888.KL",
        "name": "Axiata Group Berhad",
        "sector": "Telecommunications",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "6947.KL": {
        "symbol": "6947.KL",
        "name": "CelcomDigi Berhad",
        "sector": "Telecommunications",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "4863.KL": {
        "symbol": "4863.KL",
        "name": "Telekom Malaysia Berhad",
        "sector": "Telecommunications",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "4707.KL": {
        "symbol": "4707.KL",
        "name": "Nestle (Malaysia) Berhad",
        "sector": "Consumer Products",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "4197.KL": {
        "symbol": "4197.KL",
        "name": "Sime Darby Berhad",
        "sector": "Consumer Products",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "5819.KL": {
        "symbol": "5819.KL",
        "name": "Hong Leong Bank Berhad",
        "sector": "Financial Services",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    "1961.KL": {
        "symbol": "1961.KL",
        "name": "IOI Corporation Berhad",
        "sector": "Plantation",
        "exchange": "BURSA",
        "currency": "MYR",
    },
    # US Large Caps — currency USD, exchange US
    "AAPL": {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "sector": "Technology",
        "exchange": "US",
        "currency": "USD",
    },
    "MSFT": {
        "symbol": "MSFT",
        "name": "Microsoft Corporation",
        "sector": "Technology",
        "exchange": "US",
        "currency": "USD",
    },
    "GOOGL": {
        "symbol": "GOOGL",
        "name": "Alphabet Inc.",
        "sector": "Communication Services",
        "exchange": "US",
        "currency": "USD",
    },
    "AMZN": {
        "symbol": "AMZN",
        "name": "Amazon.com Inc.",
        "sector": "Consumer Discretionary",
        "exchange": "US",
        "currency": "USD",
    },
    "NVDA": {
        "symbol": "NVDA",
        "name": "NVIDIA Corporation",
        "sector": "Technology",
        "exchange": "US",
        "currency": "USD",
    },
    "META": {
        "symbol": "META",
        "name": "Meta Platforms Inc.",
        "sector": "Communication Services",
        "exchange": "US",
        "currency": "USD",
    },
    "TSLA": {
        "symbol": "TSLA",
        "name": "Tesla Inc.",
        "sector": "Consumer Discretionary",
        "exchange": "US",
        "currency": "USD",
    },
    "BRK-B": {
        "symbol": "BRK-B",
        "name": "Berkshire Hathaway Inc.",
        "sector": "Financial Services",
        "exchange": "US",
        "currency": "USD",
    },
    "JNJ": {
        "symbol": "JNJ",
        "name": "Johnson & Johnson",
        "sector": "Healthcare",
        "exchange": "US",
        "currency": "USD",
    },
    "V": {
        "symbol": "V",
        "name": "Visa Inc.",
        "sector": "Financial Services",
        "exchange": "US",
        "currency": "USD",
    },
    "WMT": {
        "symbol": "WMT",
        "name": "Walmart Inc.",
        "sector": "Consumer Staples",
        "exchange": "US",
        "currency": "USD",
    },
    "JPM": {
        "symbol": "JPM",
        "name": "JPMorgan Chase & Co.",
        "sector": "Financial Services",
        "exchange": "US",
        "currency": "USD",
    },
    "PG": {
        "symbol": "PG",
        "name": "Procter & Gamble Co.",
        "sector": "Consumer Staples",
        "exchange": "US",
        "currency": "USD",
    },
    "XOM": {
        "symbol": "XOM",
        "name": "Exxon Mobil Corporation",
        "sector": "Energy",
        "exchange": "US",
        "currency": "USD",
    },
    "DIS": {
        "symbol": "DIS",
        "name": "The Walt Disney Company",
        "sector": "Communication Services",
        "exchange": "US",
        "currency": "USD",
    },
    # Deterministic Synthetic Demo Symbols — currency MYR, exchange DEMO
    "DEMO1": {
        "symbol": "DEMO1",
        "name": "Demo Apex Holdings",
        "sector": "Technology",
        "exchange": "DEMO",
        "currency": "MYR",
    },
    "DEMO2": {
        "symbol": "DEMO2",
        "name": "Demo Bay Capital",
        "sector": "Financial Services",
        "exchange": "DEMO",
        "currency": "MYR",
    },
    "DEMO3": {
        "symbol": "DEMO3",
        "name": "Demo Crest Energy",
        "sector": "Energy",
        "exchange": "DEMO",
        "currency": "MYR",
    },
    "DEMO4": {
        "symbol": "DEMO4",
        "name": "Demo Delta Health",
        "sector": "Healthcare",
        "exchange": "DEMO",
        "currency": "MYR",
    },
    "DEMO5": {
        "symbol": "DEMO5",
        "name": "Demo Echo Retail",
        "sector": "Consumer Products",
        "exchange": "DEMO",
        "currency": "MYR",
    },
}

DEMO_SYMBOLS = [s for s, info in UNIVERSE.items() if info["exchange"] == "DEMO"]
LIVE_SYMBOLS = [s for s, info in UNIVERSE.items() if info["exchange"] != "DEMO"]
ALL_SYMBOLS = list(UNIVERSE.keys())


def get_universe():
    """Return all universe stock definitions as a list of dicts."""
    return list(UNIVERSE.values())


def get_demo_universe():
    """Return all demo stock definitions as a list of dicts."""
    return [info for info in UNIVERSE.values() if info["exchange"] == "DEMO"]


def get_live_universe():
    """Return all live stock definitions as a list of dicts."""
    return [info for info in UNIVERSE.values() if info["exchange"] != "DEMO"]


def get_symbol_info(symbol):
    """Return metadata dict for a symbol, or None if unknown."""
    if not symbol:
        return None
    return UNIVERSE.get(symbol.strip().upper())


def is_demo_symbol(symbol):
    """Return True if symbol is a demo symbol."""
    if not symbol:
        return False
    return symbol.strip().upper() in DEMO_SYMBOLS
