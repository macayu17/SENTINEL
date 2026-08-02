import json
from pathlib import Path
from collections import Counter

import pytest

from backend.src.data.upstox_depth import (
    UpstoxDepthError,
    UpstoxDepthRecorder,
    load_instrument_universe,
    normalize_depth_snapshot,
)


INSTRUMENT_KEY = "NSE_EQ|INE002A01018"


def _quote_payload():
    return {
        "status": "success",
        "data": {
            "NSE_EQ:RELIANCE": {
                "instrument_token": INSTRUMENT_KEY,
                "timestamp": "1785481200123",
                "last_trade_time": "1785481199987",
                "last_price": 1302.4,
                "last_trade_quantity": 3,
                "volume": 543210,
                "total_buy_quantity": 12000,
                "total_sell_quantity": 15000,
                "depth": {
                    "buy": [
                        {"price": 1302.35, "quantity": 100, "orders": 4},
                        {"price": 1302.30, "quantity": 200, "orders": 7},
                    ],
                    "sell": [
                        {"price": 1302.45, "quantity": 120, "orders": 5},
                        {"price": 1302.50, "quantity": 180, "orders": 6},
                    ],
                },
            }
        },
    }


def test_normalize_depth_snapshot_preserves_book_and_derives_metrics():
    record = normalize_depth_snapshot(
        INSTRUMENT_KEY,
        _quote_payload()["data"]["NSE_EQ:RELIANCE"],
        received_at="2026-07-31T07:00:00.000000+00:00",
    )

    assert record["schema_version"] == 1
    assert record["provider"] == "upstox"
    assert record["instrument_key"] == INSTRUMENT_KEY
    assert record["exchange_timestamp_ms"] == 1785481200123
    assert record["bids"][0] == {"price": 1302.35, "quantity": 100, "orders": 4}
    assert record["asks"][0] == {"price": 1302.45, "quantity": 120, "orders": 5}
    assert record["best_bid"] == 1302.35
    assert record["best_ask"] == 1302.45
    assert record["spread"] == pytest.approx(0.1)
    assert record["mid_price"] == pytest.approx(1302.4)
    assert record["bid_depth_5"] == 300
    assert record["ask_depth_5"] == 300
    assert record["depth_imbalance_5"] == 0.0


def test_normalize_depth_snapshot_rejects_missing_or_crossed_books():
    missing = _quote_payload()["data"]["NSE_EQ:RELIANCE"]
    missing["depth"] = {}
    with pytest.raises(UpstoxDepthError, match="missing bid or ask depth"):
        normalize_depth_snapshot(INSTRUMENT_KEY, missing)

    crossed = _quote_payload()["data"]["NSE_EQ:RELIANCE"]
    crossed["depth"]["buy"][0]["price"] = 1302.50
    with pytest.raises(UpstoxDepthError, match="crossed book"):
        normalize_depth_snapshot(INSTRUMENT_KEY, crossed)


def test_normalize_depth_snapshot_accepts_live_iso_timestamp_and_null_ltq():
    quote = _quote_payload()["data"]["NSE_EQ:RELIANCE"]
    quote["timestamp"] = "2026-07-31T13:22:15.903+05:30"
    quote["last_trade_quantity"] = None

    record = normalize_depth_snapshot(INSTRUMENT_KEY, quote)

    assert record["exchange_timestamp"] == "2026-07-31T13:22:15.903+05:30"
    assert record["exchange_timestamp_ms"] == 1785484335903
    assert record["last_trade_quantity"] == 0.0


def test_recorder_fetches_read_only_batch_and_appends_jsonl(tmp_path: Path):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return _quote_payload()

    class FakeClient:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return FakeResponse()

    client = FakeClient()
    output = tmp_path / "depth.jsonl"
    recorder = UpstoxDepthRecorder(
        access_token="secret-token",
        instrument_keys=[INSTRUMENT_KEY],
        output_path=output,
        client=client,
    )

    records = recorder.capture_once()

    assert len(records) == 1
    assert client.calls == [
        (
            "https://api.upstox.com/v2/market-quote/quotes",
            {
                "params": {"instrument_key": INSTRUMENT_KEY},
                "headers": {
                    "Accept": "application/json",
                    "Authorization": "Bearer secret-token",
                },
            },
        )
    ]
    saved = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert saved == records
    assert "secret-token" not in output.read_text(encoding="utf-8")


def test_universe_metadata_is_validated_and_written(tmp_path: Path):
    universe_path = tmp_path / "universe.json"
    universe_path.write_text(json.dumps({
        "version": "test-v1",
        "instruments": [{
            "symbol": "RELIANCE",
            "instrument_key": INSTRUMENT_KEY,
            "liquidity_bucket": "high",
            "median_daily_traded_value_inr": 123,
        }],
    }), encoding="utf-8")
    universe = load_instrument_universe(universe_path)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return _quote_payload()

    class FakeClient:
        def get(self, *args, **kwargs):
            return FakeResponse()

    row = universe["instruments"][0]
    recorder = UpstoxDepthRecorder(
        access_token="token",
        instrument_keys=[INSTRUMENT_KEY],
        output_path=tmp_path / "depth.jsonl",
        client=FakeClient(),
        universe_version=universe["version"],
        instrument_metadata={INSTRUMENT_KEY: row},
    )

    record = recorder.capture_once()[0]

    assert record["universe_version"] == "test-v1"
    assert record["symbol"] == "RELIANCE"
    assert record["liquidity_bucket"] == "high"


def test_recorder_skips_one_invalid_book_without_losing_valid_rows(tmp_path: Path):
    invalid_key = "NSE_EQ|INVALID"
    payload = _quote_payload()
    payload["data"]["NSE_EQ:INVALID"] = {
        "instrument_token": invalid_key,
        "last_price": 10,
        "depth": {},
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class FakeClient:
        def get(self, *args, **kwargs):
            return FakeResponse()

    recorder = UpstoxDepthRecorder(
        access_token="token",
        instrument_keys=[INSTRUMENT_KEY, invalid_key],
        output_path=tmp_path / "depth.jsonl",
        client=FakeClient(),
    )

    records = recorder.capture_once()

    assert [record["instrument_key"] for record in records] == [INSTRUMENT_KEY]
    assert recorder.last_skipped == {
        invalid_key: "Upstox quote is missing bid or ask depth."
    }


def test_repository_universe_has_twenty_unique_stratified_stocks():
    root = Path(__file__).resolve().parents[2]
    universe = load_instrument_universe(
        root / "backend" / "config" / "liquidity_universe.v1.json"
    )
    instruments = universe["instruments"]

    assert len(instruments) == 20
    assert len({row["instrument_key"] for row in instruments}) == 20
    assert Counter(row["liquidity_bucket"] for row in instruments) == {
        "high": 7,
        "medium": 7,
        "lower": 6,
    }
