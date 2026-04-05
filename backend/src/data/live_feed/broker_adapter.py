"""Broker/exchange adapter skeleton with streaming and polling modes.

This adapter is intentionally provider-agnostic and normalizes data to MarketState.
It is designed so a concrete broker implementation can replace payload parsing logic
without changing signal-engine inputs or dashboard schema.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional
from urllib import request

try:
    import websockets
except ImportError:  # pragma: no cover - environment dependent
    websockets = None

from .base import FeedHealth, LiveMarketFeed, MarketState
from .normalize import build_market_state
from ...utils.logger import get_logger

logger = get_logger("broker_feed")


@dataclass
class BrokerAuthConfig:
    api_key: str
    api_secret: str
    access_token: str
    account_id: str


class BrokerExchangeLiveFeedAdapter(LiveMarketFeed):
    """Broker/exchange feed adapter skeleton supporting stream + poll transport."""

    def __init__(
        self,
        *,
        symbol: str,
        duration_seconds: int,
        stream_mode: str,
        ws_url: str,
        rest_url: str,
        auth: BrokerAuthConfig,
        poll_interval_seconds: float,
        stale_after_seconds: float,
        reconnect_base_delay: float = 1.0,
        reconnect_max_delay: float = 20.0,
    ) -> None:
        self.symbol = symbol
        self.duration_seconds = duration_seconds
        self.stream_mode = stream_mode.strip().lower()
        self.ws_url = ws_url.strip()
        self.rest_url = rest_url.strip()
        self.auth = auth
        self.poll_interval_seconds = max(0.2, poll_interval_seconds)
        self.stale_after_seconds = max(1.0, stale_after_seconds)
        self.reconnect_base_delay = reconnect_base_delay
        self.reconnect_max_delay = reconnect_max_delay

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._connected = False
        self._message = "not_started"
        self._transport = "none"

        self._step = 0
        self._start_ts = time.time()
        self._last_update_ts: Optional[float] = None
        self._last_update_wall_time: Optional[float] = None

        self._bids: List[Dict[str, float]] = []
        self._asks: List[Dict[str, float]] = []
        self._recent_trades: Deque[Dict[str, Any]] = deque(maxlen=80)
        self._recent_events: Deque[Dict[str, Any]] = deque(maxlen=120)
        self._signed_flow_history: Deque[float] = deque(maxlen=240)
        self._price_history: Deque[float] = deque(maxlen=180)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        # Keep startup strict so config/auth problems are explicit and immediate.
        self._validate_runtime_requirements()

        if self.stream_mode == "stream":
            self._task = asyncio.create_task(self._run_stream_loop())
            return

        if self.stream_mode == "poll":
            self._task = asyncio.create_task(self._run_poll_loop())
            return

        if self.ws_url and websockets is not None:
            self._task = asyncio.create_task(self._run_stream_loop())
            return

        self._task = asyncio.create_task(self._run_poll_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._connected = False

    def latest_state(self) -> Optional[MarketState]:
        if not self._running:
            return None
        if not self._bids or not self._asks:
            return None

        self._step += 1
        elapsed = time.time() - self._start_ts
        state = build_market_state(
            step=self._step,
            current_time=float(elapsed),
            duration_seconds=self.duration_seconds,
            bids=self._bids[:10],
            asks=self._asks[:10],
            price_history=list(self._price_history),
            signed_flow_history=self._signed_flow_history,
            recent_trades=list(self._recent_trades),
            recent_events=list(self._recent_events),
            recent_orders=[],
        )
        return state

    def health(self) -> FeedHealth:
        now = time.time()
        stale = False
        latency_ms: Optional[float] = None
        if self._last_update_wall_time is not None:
            age_seconds = max(0.0, now - self._last_update_wall_time)
            stale = age_seconds > self.stale_after_seconds
            latency_ms = age_seconds * 1000.0

        return FeedHealth(
            connected=self._connected,
            source="broker",
            provider="broker",
            last_update_ts=self._last_update_ts,
            last_update_wall_time=self._last_update_wall_time,
            fallback_active=False,
            stale=stale,
            latency_ms=latency_ms,
            transport=self._transport,
            message=self._message,
        )

    def _validate_runtime_requirements(self) -> None:
        if not (self.auth.api_key or self.auth.access_token):
            raise RuntimeError(
                "Broker auth missing: set BROKER_API_KEY or BROKER_ACCESS_TOKEN."
            )
        if self.stream_mode in {"stream", "auto"} and self.ws_url and websockets is None:
            raise RuntimeError(
                "websockets package is required for broker stream mode."
            )
        if self.stream_mode == "stream" and not self.ws_url:
            raise RuntimeError("BROKER_WS_URL is required for broker stream mode.")
        if self.stream_mode == "poll" and not self.rest_url:
            raise RuntimeError("BROKER_REST_URL is required for broker poll mode.")
        if self.stream_mode == "auto" and not (self.ws_url or self.rest_url):
            raise RuntimeError(
                "Broker auto mode requires BROKER_WS_URL or BROKER_REST_URL."
            )

    async def _run_stream_loop(self) -> None:
        if not self.ws_url:
            raise RuntimeError("BROKER_WS_URL is required for stream transport.")

        self._transport = "stream"
        backoff = self.reconnect_base_delay
        attempts = 0

        while self._running:
            try:
                self._message = "connecting_stream"
                assert websockets is not None
                async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=20) as ws:
                    self._connected = True
                    self._message = "connected_stream"
                    attempts = 0
                    backoff = self.reconnect_base_delay
                    logger.info("Broker stream connected")
                    self._record_event("Kernel", "Broker stream connected", "info")

                    await self._subscribe_stream(ws)

                    while self._running:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        payload = json.loads(raw)
                        self._handle_payload(payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                attempts += 1
                self._connected = False
                self._message = f"stream_reconnect_attempt_{attempts}: {exc}"
                logger.warning(f"Broker stream error, reconnect attempt {attempts}: {exc}")
                self._record_event(
                    "Kernel",
                    f"Broker stream reconnect attempt {attempts}: {exc}",
                    "warning",
                )
                await asyncio.sleep(backoff)
                backoff = min(self.reconnect_max_delay, backoff * 2)

                if self.stream_mode == "auto" and self.rest_url:
                    logger.warning("Broker stream unavailable, switching to poll fallback")
                    self._record_event(
                        "Kernel",
                        "Broker stream unavailable; switched to poll fallback",
                        "warning",
                    )
                    await self._run_poll_loop()
                    return

    async def _run_poll_loop(self) -> None:
        if not self.rest_url:
            raise RuntimeError("BROKER_REST_URL is required for poll transport.")

        self._transport = "poll"
        backoff = self.reconnect_base_delay
        attempts = 0
        self._message = "connected_poll"

        while self._running:
            try:
                payload = await asyncio.to_thread(self._fetch_poll_payload)
                self._connected = True
                self._message = "connected_poll"
                attempts = 0
                backoff = self.reconnect_base_delay
                self._handle_payload(payload)
                await asyncio.sleep(self.poll_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                attempts += 1
                self._connected = False
                self._message = f"poll_reconnect_attempt_{attempts}: {exc}"
                logger.warning(f"Broker poll error, retry attempt {attempts}: {exc}")
                self._record_event(
                    "Kernel",
                    f"Broker poll retry attempt {attempts}: {exc}",
                    "warning",
                )
                await asyncio.sleep(backoff)
                backoff = min(self.reconnect_max_delay, backoff * 2)

    async def _subscribe_stream(self, ws: Any) -> None:
        subscribe_message = {
            "action": "subscribe",
            "symbol": self.symbol,
            "channels": ["book", "trades"],
        }
        await ws.send(json.dumps(subscribe_message))

    def _fetch_poll_payload(self) -> Dict[str, Any]:
        url = f"{self.rest_url}?symbol={self.symbol}"
        req = request.Request(url, headers=self._auth_headers(), method="GET")
        with request.urlopen(req, timeout=10) as response:  # nosec B310
            body = response.read().decode("utf-8")
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise RuntimeError("Broker poll endpoint returned non-object payload")
        return payload

    def _auth_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth.access_token:
            headers["Authorization"] = f"Bearer {self.auth.access_token}"
        if self.auth.api_key:
            headers["X-API-Key"] = self.auth.api_key
        return headers

    def _handle_payload(self, payload: Dict[str, Any]) -> None:
        bids = self._extract_levels(payload.get("bids") or payload.get("book", {}).get("bids"))
        asks = self._extract_levels(payload.get("asks") or payload.get("book", {}).get("asks"))
        if bids:
            self._bids = bids
        if asks:
            self._asks = asks

        for trade in self._extract_trades(payload):
            self._recent_trades.append(trade)
            signed_flow = float(trade.get("quantity", 0.0))
            if trade.get("aggressor_side") == "SELL":
                signed_flow = -signed_flow
            self._signed_flow_history.append(signed_flow)

        if self._bids and self._asks:
            best_bid = float(self._bids[0]["price"])
            best_ask = float(self._asks[0]["price"])
            self._price_history.append((best_bid + best_ask) / 2.0)

        elapsed = float(time.time() - self._start_ts)
        self._last_update_ts = elapsed
        self._last_update_wall_time = time.time()

    def _extract_levels(self, raw_levels: Any) -> List[Dict[str, float]]:
        levels: List[Dict[str, float]] = []
        if not isinstance(raw_levels, list):
            return levels

        for row in raw_levels[:20]:
            if isinstance(row, dict):
                price = row.get("price")
                size = row.get("size")
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                price, size = row[0], row[1]
            else:
                continue

            try:
                p = float(price)
                q = float(size)
            except (TypeError, ValueError):
                continue

            if p > 0 and q >= 0:
                levels.append({"price": p, "size": q})

        return levels

    def _extract_trades(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_trades = payload.get("trades")
        if isinstance(raw_trades, dict):
            raw_trades = [raw_trades]
        if not isinstance(raw_trades, list):
            return []

        normalized: List[Dict[str, Any]] = []
        elapsed = float(time.time() - self._start_ts)

        for i, trade in enumerate(raw_trades[:20]):
            if not isinstance(trade, dict):
                continue
            try:
                price = float(trade.get("price", 0.0))
                quantity = float(trade.get("quantity", trade.get("qty", 0.0)))
            except (TypeError, ValueError):
                continue
            if price <= 0 or quantity <= 0:
                continue

            side_raw = str(trade.get("side", trade.get("aggressor_side", "BUY"))).upper()
            side = "SELL" if side_raw.startswith("S") else "BUY"
            normalized.append(
                {
                    "ts": float(trade.get("ts", elapsed)),
                    "trade_id": str(trade.get("trade_id", trade.get("id", f"BRK-{self._step}-{i}"))),
                    "price": price,
                    "quantity": int(quantity),
                    "buyer_agent_id": "BROKER_BUYER",
                    "seller_agent_id": "BROKER_SELLER",
                    "aggressor_side": side,
                }
            )

        return normalized

    def _record_event(self, event_type: str, message: str, severity: str) -> None:
        self._recent_events.append(
            {
                "ts": float(time.time() - self._start_ts),
                "type": event_type,
                "severity": severity,
                "message": message,
                "metadata": {"provider": "broker", "transport": self._transport},
            }
        )

    @staticmethod
    def provider_name() -> str:
        return "broker"
