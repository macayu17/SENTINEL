import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.data import upstox_provider
from backend.src.data.upstox_provider import (
    UpstoxCredentialsError,
    UpstoxDataError,
    UpstoxHistoricalProvider,
    UpstoxInstrument,
    UpstoxQuote,
    fetch_upstox_full_quote,
    fetch_upstox_ltp_quote,
    upstox_candles_to_stock_info,
    normalize_upstox_candles,
    normalize_upstox_full_quote,
    normalize_upstox_instruments,
    normalize_upstox_ltp,
    search_upstox_instruments,
    validate_upstox_interval,
)


def test_upstox_provider_requires_server_token(monkeypatch):
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("UPSTOX_ANALYTICS_TOKEN", raising=False)
    monkeypatch.setattr(upstox_provider, "_reload_environment_values", lambda names: None)

    with pytest.raises(UpstoxCredentialsError, match="UPSTOX_ACCESS_TOKEN"):
        UpstoxHistoricalProvider()


def test_upstox_provider_normalizes_v3_historical_candles_payload():
    payload = {
        "status": "success",
        "data": {
            "candles": [
                ["2025-01-01T09:15:00+05:30", 1250.0, 1261.5, 1244.8, 1258.2, 120000, 0],
                ["2025-01-01T09:45:00+05:30", 1258.2, 1264.0, 1256.1, 1260.5, 99000, 5],
            ]
        },
    }

    candles = normalize_upstox_candles(payload)
    info = upstox_candles_to_stock_info(
        instrument_key="NSE_EQ|INE002A01018",
        candles=candles,
        unit="minutes",
        interval="30",
    )

    assert [c.close for c in candles] == [1258.2, 1260.5]
    assert candles[0].volume == 120000
    assert candles[0].oi == 0
    assert candles[1].oi == 5
    assert info.ticker == "NSE_EQ|INE002A01018"
    assert info.name == "NSE_EQ|INE002A01018 Upstox minutes/30"
    assert info.currency == "INR"
    assert info.bars == 2
    assert info.prices == [1258.2, 1260.5]
    assert info.period_start == "2025-01-01T09:15:00+05:30"
    assert info.period_end == "2025-01-01T09:45:00+05:30"


@pytest.mark.parametrize(
    ("unit", "interval"),
    [
        ("minutes", "1"),
        ("minutes", "300"),
        ("hours", "5"),
        ("days", "1"),
        ("weeks", "1"),
        ("months", "1"),
    ],
)
def test_upstox_interval_accepts_documented_v3_values(unit, interval):
    validate_upstox_interval(unit, interval)


@pytest.mark.parametrize(
    ("unit", "interval"),
    [
        ("minutes", "301"),
        ("hours", "6"),
        ("days", "2"),
        ("invalid", "1"),
    ],
)
def test_upstox_interval_rejects_unsupported_values(unit, interval):
    with pytest.raises(ValueError):
        validate_upstox_interval(unit, interval)


def test_upstox_instrument_search_normalizes_documented_response():
    payload = {
        "status": "success",
        "data": [
            {
                "name": "RELIANCE INDUSTRIES LTD",
                "segment": "NSE_EQ",
                "exchange": "NSE",
                "isin": "INE002A01018",
                "instrument_key": "NSE_EQ|INE002A01018",
                "trading_symbol": "RELIANCE",
                "short_name": "Reliance",
                "instrument_type": "EQ",
            }
        ],
        "meta_data": {"page": {"total_records": 1}},
    }

    instruments = normalize_upstox_instruments(payload)

    assert instruments == [
        UpstoxInstrument(
            instrument_key="NSE_EQ|INE002A01018",
            trading_symbol="RELIANCE",
            name="RELIANCE INDUSTRIES LTD",
            exchange="NSE",
            segment="NSE_EQ",
            instrument_type="EQ",
            isin="INE002A01018",
            short_name="Reliance",
        )
    ]


def test_upstox_instrument_search_rejection_names_search_context():
    with pytest.raises(UpstoxDataError, match="Upstox instrument search request was rejected."):
        normalize_upstox_instruments({"status": "error", "errors": []})


def test_upstox_provider_searches_instruments_with_v2_filters():
    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "success",
                "data": [
                    {
                        "instrument_key": "NSE_EQ|INE002A01018",
                        "trading_symbol": "RELIANCE",
                        "name": "RELIANCE INDUSTRIES LTD",
                        "exchange": "NSE",
                        "segment": "NSE_EQ",
                        "instrument_type": "EQ",
                    }
                ],
            }

    class FakeClient:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return FakeResponse()

    client = FakeClient()
    provider = UpstoxHistoricalProvider(
        access_token="token",
        base_url="https://api.upstox.com/v3",
        v2_base_url="https://api.upstox.com/v2",
        http_client=client,
    )

    instruments = search_upstox_instruments(
        query="Reliance",
        exchanges="NSE",
        segments="EQ",
        records=5,
        provider=provider,
    )

    assert instruments[0].instrument_key == "NSE_EQ|INE002A01018"
    assert client.calls[0][0] == "https://api.upstox.com/v2/instruments/search"
    assert client.calls[0][1]["params"] == {
        "query": "Reliance",
        "exchanges": "NSE",
        "segments": "EQ",
        "page_number": 1,
        "records": 5,
    }


def test_upstox_ltp_normalizes_v3_response():
    payload = {
        "status": "success",
        "data": {
            "NSE_EQ:RELIANCE": {
                "last_price": 2520.35,
                "instrument_token": "NSE_EQ|INE002A01018",
                "ltq": 7,
                "volume": 123456,
                "cp": 2501.0,
            }
        },
    }

    quote = normalize_upstox_ltp(payload, "NSE_EQ|INE002A01018")

    assert quote == UpstoxQuote(
        instrument_key="NSE_EQ|INE002A01018",
        last_price=2520.35,
        ltq=7,
        volume=123456,
        previous_close=2501.0,
    )


def test_upstox_full_quote_normalizes_live_depth_response():
    payload = {
        "status": "success",
        "data": {
            "NSE_EQ:RELIANCE": {
                "instrument_token": "NSE_EQ|INE002A01018",
                "last_price": 2520.35,
                "volume": 123456,
                "ohlc": {"close": 2501.0},
                "total_buy_quantity": 5000,
                "total_sell_quantity": 7000,
                "timestamp": "1747984841612",
                "depth": {
                    "buy": [
                        {"quantity": 1200, "price": 2520.25, "orders": 12},
                        {"quantity": 800, "price": 2520.2, "orders": 9},
                        {"quantity": 0, "price": 0, "orders": 0},
                    ],
                    "sell": [
                        {"quantity": 900, "price": 2520.45, "orders": 7},
                        {"quantity": 1000, "price": 2520.5, "orders": 8},
                    ],
                },
            }
        },
    }

    quote = normalize_upstox_full_quote(payload, "NSE_EQ|INE002A01018")

    assert quote.instrument_key == "NSE_EQ|INE002A01018"
    assert quote.last_price == 2520.35
    assert quote.previous_close == 2501.0
    assert quote.total_buy_quantity == 5000
    assert quote.total_sell_quantity == 7000
    assert quote.depth_source == "provider_live"
    assert quote.order_book == {
        "bids": [
            {"price": 2520.25, "size": 1200, "orders": 12},
            {"price": 2520.2, "size": 800, "orders": 9},
        ],
        "asks": [
            {"price": 2520.45, "size": 900, "orders": 7},
            {"price": 2520.5, "size": 1000, "orders": 8},
        ],
    }


def test_upstox_full_quote_without_depth_marks_modeled_live_fallback():
    payload = {
        "status": "success",
        "data": {
            "NSE_EQ:RELIANCE": {
                "instrument_token": "NSE_EQ|INE002A01018",
                "last_price": 2520.35,
                "volume": 123456,
                "ohlc": {"close": 2501.0},
                "total_buy_quantity": 5000,
                "total_sell_quantity": 7000,
                "timestamp": "1747984841612",
            }
        },
    }

    quote = normalize_upstox_full_quote(payload, "NSE_EQ|INE002A01018")

    assert quote.depth_source == "modeled_live_fallback"
    assert quote.order_book is None


def test_upstox_provider_fetches_ltp_from_v3_market_quote():
    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "success",
                "data": {
                    "NSE_EQ:RELIANCE": {
                        "last_price": 2520.35,
                        "instrument_token": "NSE_EQ|INE002A01018",
                        "ltq": 7,
                        "volume": 123456,
                        "cp": 2501.0,
                    }
                },
            }

    class FakeClient:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return FakeResponse()

    client = FakeClient()
    provider = UpstoxHistoricalProvider(
        access_token="token",
        base_url="https://api.upstox.com/v3",
        http_client=client,
    )

    quote = fetch_upstox_ltp_quote(instrument_key="NSE_EQ|INE002A01018", provider=provider)

    assert quote.last_price == 2520.35
    assert client.calls[0][0] == "https://api.upstox.com/v3/market-quote/ltp"
    assert client.calls[0][1]["params"] == {"instrument_key": "NSE_EQ|INE002A01018"}


def test_upstox_provider_fetches_full_quote_from_v2_market_quote():
    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "success",
                "data": {
                    "NSE_EQ:RELIANCE": {
                        "last_price": 2520.35,
                        "instrument_token": "NSE_EQ|INE002A01018",
                        "depth": {
                            "buy": [{"quantity": 1200, "price": 2520.25, "orders": 12}],
                            "sell": [{"quantity": 900, "price": 2520.45, "orders": 7}],
                        },
                    }
                },
            }

    class FakeClient:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return FakeResponse()

    client = FakeClient()
    provider = UpstoxHistoricalProvider(
        access_token="token",
        base_url="https://api.upstox.com/v3",
        v2_base_url="https://api.upstox.com/v2",
        http_client=client,
    )

    quote = fetch_upstox_full_quote(instrument_key="NSE_EQ|INE002A01018", provider=provider)

    assert quote.last_price == 2520.35
    assert quote.order_book["bids"][0]["size"] == 1200
    assert client.calls[0][0] == "https://api.upstox.com/v2/market-quote/quotes"
    assert client.calls[0][1]["params"] == {"instrument_key": "NSE_EQ|INE002A01018"}
