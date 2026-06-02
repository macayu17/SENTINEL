import sys
from pathlib import Path

import math
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from backend.src.data import groww_provider
from backend.src.data.groww_provider import (
    GrowwCredentialsError,
    GrowwDataError,
    GrowwHistoricalProvider,
    _resolve_interval_constant,
    fetch_groww_quote,
    groww_candles_to_stock_info,
    normalize_groww_candles,
    normalize_groww_quote,
)


def test_groww_provider_requires_server_auth_token(monkeypatch):
    monkeypatch.delenv("GROWW_API_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("GROWW_API_KEY", raising=False)
    monkeypatch.delenv("GROWW_API_SECRET", raising=False)
    monkeypatch.setattr(groww_provider, "_reload_environment_values", lambda names: None)

    with pytest.raises(GrowwCredentialsError, match="GROWW_API_AUTH_TOKEN"):
        GrowwHistoricalProvider()


def test_groww_provider_normalizes_backtesting_candles_payload():
    payload = {
        "candles": [
            ["2025-09-24T10:30:00", 245.95, 246.15, 245.05, 245.6, 735060, None],
            ["2025-09-24T11:00:00", 245.64, 245.66, 244.8, 244.94, 682373, 112.0],
        ],
        "start_time": "2025-09-24 10:30:00",
        "end_time": "2025-09-24 11:00:00",
        "interval_in_minutes": 30,
    }

    candles = normalize_groww_candles(payload)
    info = groww_candles_to_stock_info(
        groww_symbol="NSE-WIPRO",
        candles=candles,
        exchange="NSE",
        segment="CASH",
    )

    assert [c.close for c in candles] == [245.6, 244.94]
    assert candles[0].volume == 735060
    assert candles[0].oi is None
    assert candles[1].oi == 112.0
    assert info.ticker == "NSE-WIPRO"
    assert info.name == "NSE-WIPRO Groww CASH"
    assert info.currency == "INR"
    assert info.bars == 2
    assert info.prices == [245.6, 244.94]
    assert info.period_start == "2025-09-24T10:30:00"
    assert info.period_end == "2025-09-24T11:00:00"


def test_groww_intraday_volatility_uses_candle_interval_scale():
    payload = {
        "candles": [
            ["2025-09-24T09:15:00", 100.0, 101.0, 99.5, 100.0, 1000],
            ["2025-09-24T09:45:00", 100.0, 102.0, 99.8, 101.5, 1200],
            ["2025-09-24T10:15:00", 101.5, 102.2, 98.8, 99.5, 1400],
            ["2025-09-24T10:45:00", 99.5, 103.1, 99.0, 102.5, 1600],
        ],
    }
    candles = normalize_groww_candles(payload)
    returns = [
        math.log(candles[i].close / candles[i - 1].close)
        for i in range(1, len(candles))
    ]
    daily_scaled_vol = round(float(np.std(returns) * np.sqrt(252)), 4)
    expected_intraday_vol = round(float(np.std(returns) * np.sqrt(252 * (375 / 30))), 4)

    info = groww_candles_to_stock_info(
        groww_symbol="NSE-WIPRO",
        candles=candles,
        exchange="NSE",
        segment="CASH",
        candle_interval="MIN_30",
    )

    assert info.realized_vol == expected_intraday_vol
    assert info.realized_vol > daily_scaled_vol


def test_groww_interval_aliases_match_sdk_constants():
    class FakeGrowwClient:
        CANDLE_INTERVAL_DAY = "1day"
        CANDLE_INTERVAL_WEEK = "1week"
        CANDLE_INTERVAL_MONTH = "1month"

    client = FakeGrowwClient()

    assert _resolve_interval_constant(client, "DAY_1") == "1day"
    assert _resolve_interval_constant(client, "WEEK_1") == "1week"
    assert _resolve_interval_constant(client, "MONTH_1") == "1month"


def test_groww_quote_normalizes_live_depth_payload():
    payload = {
        "last_price": 149.5,
        "last_trade_quantity": 500,
        "volume": 10000,
        "ohlc": {"close": 149.5},
        "total_buy_quantity": 5000,
        "total_sell_quantity": 4000,
        "depth": {
            "buy": [
                {"price": 149.4, "quantity": 1000},
                {"price": 149.35, "quantity": 700},
            ],
            "sell": [
                {"price": 149.6, "quantity": 900},
                {"price": 149.65, "quantity": 600},
            ],
        },
    }

    quote = normalize_groww_quote(
        payload,
        exchange="NSE",
        segment="CASH",
        groww_symbol="RELIANCE",
    )

    assert quote.groww_symbol == "NSE-RELIANCE"
    assert quote.last_price == 149.5
    assert quote.ltq == 500
    assert quote.total_buy_quantity == 5000
    assert quote.total_sell_quantity == 4000
    assert quote.depth_source == "provider_live"
    assert quote.order_book == {
        "bids": [
            {"price": 149.4, "size": 1000},
            {"price": 149.35, "size": 700},
        ],
        "asks": [
            {"price": 149.6, "size": 900},
            {"price": 149.65, "size": 600},
        ],
    }


def test_groww_quote_reports_quote_field_errors():
    with pytest.raises(GrowwDataError, match="Groww quote last price is not numeric."):
        normalize_groww_quote(
            {"last_price": "not-a-price"},
            exchange="NSE",
            segment="CASH",
            groww_symbol="RELIANCE",
        )

    with pytest.raises(GrowwDataError, match="Groww total buy quantity is not numeric."):
        normalize_groww_quote(
            {"last_price": 149.5, "total_buy_quantity": "not-a-quantity"},
            exchange="NSE",
            segment="CASH",
            groww_symbol="RELIANCE",
        )


def test_groww_provider_fetches_live_quote_with_trading_symbol():
    class FakeGrowwClient:
        EXCHANGE_NSE = "NSE"
        SEGMENT_CASH = "CASH"

        def __init__(self):
            self.calls = []

        def get_quote(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "last_price": 149.5,
                "depth": {
                    "buy": [{"price": 149.4, "quantity": 1000}],
                    "sell": [{"price": 149.6, "quantity": 900}],
                },
            }

    client = FakeGrowwClient()
    provider = GrowwHistoricalProvider(client=client)

    quote = fetch_groww_quote(
        exchange="NSE",
        segment="CASH",
        groww_symbol="NSE-RELIANCE",
        provider=provider,
    )

    assert quote.last_price == 149.5
    assert quote.order_book["asks"][0]["price"] == 149.6
    assert client.calls == [
        {"exchange": "NSE", "segment": "CASH", "trading_symbol": "RELIANCE"}
    ]
