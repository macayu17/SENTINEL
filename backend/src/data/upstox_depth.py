"""Read-only Upstox depth snapshot recording."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx

from ..utils.config import _reload_environment_values


UPSTOX_FULL_QUOTE_URL = "https://api.upstox.com/v2/market-quote/quotes"


class UpstoxDepthError(RuntimeError):
    """Raised when a depth snapshot cannot be safely recorded."""


def load_instrument_universe(path: Path) -> dict[str, Any]:
    try:
        universe = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UpstoxDepthError(f"Cannot load instrument universe: {path}.") from exc
    instruments = universe.get("instruments") if isinstance(universe, dict) else None
    if not universe.get("version") or not isinstance(instruments, list) or not instruments:
        raise UpstoxDepthError("Instrument universe requires a version and instruments.")

    keys: set[str] = set()
    for instrument in instruments:
        if not isinstance(instrument, dict):
            raise UpstoxDepthError("Instrument universe rows must be objects.")
        key = str(instrument.get("instrument_key", "")).strip()
        symbol = str(instrument.get("symbol", "")).strip()
        bucket = instrument.get("liquidity_bucket")
        if not key or not symbol or bucket not in {"high", "medium", "lower"}:
            raise UpstoxDepthError("Instrument universe contains an invalid row.")
        if key in keys:
            raise UpstoxDepthError(f"Instrument universe contains duplicate key {key}.")
        keys.add(key)
    return universe


def _finite_number(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise UpstoxDepthError(f"Upstox {label} is not numeric.") from exc
    if not math.isfinite(number):
        raise UpstoxDepthError(f"Upstox {label} is not finite.")
    return number


def _timestamp_ms(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(datetime.fromisoformat(str(value)).timestamp() * 1000)
        except ValueError as exc:
            raise UpstoxDepthError("Upstox timestamp is not epoch milliseconds or ISO-8601.") from exc


def _normalize_side(rows: Any, *, reverse: bool) -> list[dict[str, float | int]]:
    if not isinstance(rows, list):
        return []

    levels: list[dict[str, float | int]] = []
    for row in rows[:5]:
        if not isinstance(row, dict):
            continue
        price = _finite_number(row.get("price"), "depth price")
        quantity = int(_finite_number(row.get("quantity"), "depth quantity"))
        orders = int(_finite_number(row.get("orders", 0), "depth order count"))
        if price <= 0 or quantity <= 0:
            continue
        levels.append({"price": price, "quantity": quantity, "orders": max(0, orders)})
    levels.sort(key=lambda level: level["price"], reverse=reverse)
    return levels


def normalize_depth_snapshot(
    instrument_key: str,
    quote: Any,
    *,
    received_at: Optional[str] = None,
) -> dict[str, Any]:
    """Validate one quote and retain both raw depth and basic derived values."""
    if not isinstance(quote, dict):
        raise UpstoxDepthError("Upstox quote was not an object.")

    depth = quote.get("depth")
    depth = depth if isinstance(depth, dict) else {}
    bids = _normalize_side(depth.get("buy"), reverse=True)
    asks = _normalize_side(depth.get("sell"), reverse=False)
    if not bids or not asks:
        raise UpstoxDepthError("Upstox quote is missing bid or ask depth.")

    best_bid = float(bids[0]["price"])
    best_ask = float(asks[0]["price"])
    if best_bid >= best_ask:
        raise UpstoxDepthError("Upstox quote contains a crossed book.")

    bid_depth = sum(int(level["quantity"]) for level in bids)
    ask_depth = sum(int(level["quantity"]) for level in asks)
    total_depth = bid_depth + ask_depth
    mid_price = (best_bid + best_ask) / 2.0
    spread = best_ask - best_bid

    return {
        "schema_version": 1,
        "provider": "upstox",
        "received_at": received_at or datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "exchange_timestamp": str(quote["timestamp"]) if quote.get("timestamp") else None,
        "exchange_timestamp_ms": _timestamp_ms(quote.get("timestamp")),
        "last_trade_timestamp_ms": _timestamp_ms(quote.get("last_trade_time")),
        "instrument_key": instrument_key,
        "last_price": _finite_number(quote.get("last_price"), "last price"),
        "last_trade_quantity": _finite_number(
            quote.get("last_trade_quantity") or quote.get("ltq") or 0,
            "last trade quantity",
        ),
        "volume": _finite_number(quote.get("volume", 0), "volume"),
        "total_buy_quantity": _finite_number(
            quote.get("total_buy_quantity", 0),
            "total buy quantity",
        ),
        "total_sell_quantity": _finite_number(
            quote.get("total_sell_quantity", 0),
            "total sell quantity",
        ),
        "bids": bids,
        "asks": asks,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid_price": mid_price,
        "spread": spread,
        "spread_bps": spread / mid_price * 10_000.0,
        "bid_depth_5": bid_depth,
        "ask_depth_5": ask_depth,
        "depth_imbalance_5": (bid_depth - ask_depth) / total_depth,
    }


class UpstoxDepthRecorder:
    """Append validated full-quote snapshots to a local JSONL dataset."""

    def __init__(
        self,
        *,
        instrument_keys: Iterable[str],
        output_path: Path,
        access_token: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        universe_version: Optional[str] = None,
        instrument_metadata: Optional[dict[str, dict[str, Any]]] = None,
    ) -> None:
        keys = list(dict.fromkeys(key.strip() for key in instrument_keys if key.strip()))
        if not keys:
            raise ValueError("At least one Upstox instrument key is required.")
        if len(keys) > 500:
            raise ValueError("Upstox full quotes support at most 500 instrument keys per request.")

        _reload_environment_values(["UPSTOX_ACCESS_TOKEN", "UPSTOX_ANALYTICS_TOKEN"])
        token = access_token or os.getenv("UPSTOX_ACCESS_TOKEN") or os.getenv("UPSTOX_ANALYTICS_TOKEN")
        if not token:
            raise UpstoxDepthError(
                "Set UPSTOX_ACCESS_TOKEN or UPSTOX_ANALYTICS_TOKEN in backend/.env."
            )

        self.instrument_keys = keys
        self.output_path = Path(output_path)
        self.universe_version = universe_version
        self.instrument_metadata = instrument_metadata or {}
        self._headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
        self._client = client or httpx.Client(timeout=15.0)
        self.last_skipped: dict[str, str] = {}

    def capture_once(self) -> list[dict[str, Any]]:
        response = self._client.get(
            UPSTOX_FULL_QUOTE_URL,
            params={"instrument_key": ",".join(self.instrument_keys)},
            headers=self._headers,
        )
        try:
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise UpstoxDepthError("Upstox full-quote request failed.") from exc

        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise UpstoxDepthError("Upstox full-quote request was rejected.")
        quotes = payload.get("data")
        if not isinstance(quotes, dict):
            raise UpstoxDepthError("Upstox full-quote response has no data object.")

        received_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        records: list[dict[str, Any]] = []
        self.last_skipped = {}
        for instrument_key in self.instrument_keys:
            quote = next(
                (
                    value
                    for value in quotes.values()
                    if isinstance(value, dict)
                    and value.get("instrument_token") == instrument_key
                ),
                None,
            )
            if quote is None:
                self.last_skipped[instrument_key] = "quote missing from response"
                continue
            try:
                record = normalize_depth_snapshot(
                    instrument_key,
                    quote,
                    received_at=received_at,
                )
            except UpstoxDepthError as exc:
                self.last_skipped[instrument_key] = str(exc)
                continue
            metadata = self.instrument_metadata.get(instrument_key)
            if metadata:
                record.update({
                    "universe_version": self.universe_version,
                    "symbol": metadata["symbol"],
                    "liquidity_bucket": metadata["liquidity_bucket"],
                    "median_daily_traded_value_inr": metadata["median_daily_traded_value_inr"],
                })
            records.append(record)

        if not records:
            raise UpstoxDepthError("Upstox returned no recordable depth books.")

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8", newline="\n") as output:
            for record in records:
                output.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
        return records
