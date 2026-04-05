"""Binance WebSocket adapter for LIVE_SHADOW market data ingestion."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

try:
    import websockets
except ImportError:  # pragma: no cover - environment dependent
    websockets = None

from .base import FeedHealth, LiveMarketFeed, MarketState
from .normalize import build_market_state
from ...utils.logger import get_logger

logger = get_logger("binance_feed")


class BinanceLiveFeedAdapter(LiveMarketFeed):
    def __init__(
        self,
        symbol: str = "btcusdt",
        duration_seconds: int = 23_400,
        reconnect_base_delay: float = 1.0,
        reconnect_max_delay: float = 20.0,
    ) -> None:
        self.symbol = symbol.lower()
        self.duration_seconds = duration_seconds
        self.reconnect_base_delay = reconnect_base_delay
        self.reconnect_max_delay = reconnect_max_delay

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._connected = False
        self._connection_message = "not_started"
        self._last_update_ts: Optional[float] = None
        self._last_update_wall_time: Optional[float] = None

        self._step = 0
        self._start_ts = time.time()

        self._best_bid: Optional[float] = None
        self._best_ask: Optional[float] = None
        self._bids: List[Dict[str, float]] = []
        self._asks: List[Dict[str, float]] = []

        self._price_history: Deque[float] = deque(maxlen=120)
        self._signed_flow_history: Deque[float] = deque(maxlen=200)
        self._recent_trades: Deque[Dict[str, Any]] = deque(maxlen=40)
        self._recent_events: Deque[Dict[str, Any]] = deque(maxlen=80)

    async def start(self) -> None:
        if self._running:
            return
        if websockets is None:
            raise RuntimeError("websockets package is required for BinanceLiveFeedAdapter")
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

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

    def health(self) -> FeedHealth:
        latency_ms = None
        stale = False
        if self._last_update_wall_time is not None:
            age_seconds = max(0.0, time.time() - self._last_update_wall_time)
            latency_ms = age_seconds * 1000.0
            stale = age_seconds > 6.0

        return FeedHealth(
            connected=self._connected,
            source="binance",
            provider="binance",
            last_update_ts=self._last_update_ts,
            last_update_wall_time=self._last_update_wall_time,
            fallback_active=False,
            stale=stale,
            latency_ms=latency_ms,
            transport="stream",
            message=self._connection_message,
        )

    def latest_state(self) -> Optional[MarketState]:
        if not self._connected:
            return None
        if self._best_bid is None or self._best_ask is None:
            return None

        bids = self._bids[:10] if self._bids else [{"price": float(self._best_bid), "size": 1.0}]
        asks = self._asks[:10] if self._asks else [{"price": float(self._best_ask), "size": 1.0}]

        self._step += 1
        elapsed = time.time() - self._start_ts
        state = build_market_state(
            step=self._step,
            current_time=float(elapsed),
            duration_seconds=self.duration_seconds,
            bids=bids,
            asks=asks,
            price_history=list(self._price_history),
            signed_flow_history=self._signed_flow_history,
            recent_trades=list(self._recent_trades),
            recent_events=list(self._recent_events),
            recent_orders=[],
        )
        if state is not None:
            self._last_update_ts = state.current_time
            self._last_update_wall_time = time.time()
        return state

    async def _run_loop(self) -> None:
        streams = "/".join(
            [
                f"{self.symbol}@bookTicker",
                f"{self.symbol}@depth10@100ms",
                f"{self.symbol}@trade",
            ]
        )
        url = f"wss://stream.binance.com:9443/stream?streams={streams}"

        backoff = self.reconnect_base_delay
        while self._running:
            try:
                self._connection_message = "connecting"
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    self._connected = True
                    self._connection_message = "connected"
                    backoff = self.reconnect_base_delay
                    logger.info("Connected to Binance stream")
                    self._record_event("Kernel", "Connected to Binance stream", "info")

                    while self._running:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        payload = json.loads(raw)
                        self._handle_stream_payload(payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._connected = False
                self._connection_message = f"reconnecting_after_error: {exc}"
                logger.warning(f"Binance stream error: {exc}")
                self._record_event("Kernel", f"Binance reconnect: {exc}", "warning")
                await asyncio.sleep(backoff)
                backoff = min(self.reconnect_max_delay, backoff * 2)

    def _handle_stream_payload(self, payload: Dict[str, Any]) -> None:
        stream = payload.get("stream", "")
        data = payload.get("data", {})

        if stream.endswith("@bookticker"):
            bid = float(data.get("b", 0.0))
            ask = float(data.get("a", 0.0))
            if bid > 0 and ask > 0:
                self._best_bid = bid
                self._best_ask = ask
                self._price_history.append((bid + ask) / 2)
            return

        if "@depth" in stream:
            raw_bids = data.get("b", [])
            raw_asks = data.get("a", [])
            self._bids = [{"price": float(p), "size": float(q)} for p, q in raw_bids[:10]]
            self._asks = [{"price": float(p), "size": float(q)} for p, q in raw_asks[:10]]
            return

        if stream.endswith("@trade"):
            price = float(data.get("p", 0.0))
            qty = float(data.get("q", 0.0))
            maker_is_buyer = bool(data.get("m", False))
            signed_flow = -qty if maker_is_buyer else qty
            self._signed_flow_history.append(signed_flow)

            self._recent_trades.append(
                {
                    "ts": float((data.get("E", 0) or 0) / 1000.0),
                    "trade_id": str(data.get("t", "")),
                    "price": price,
                    "quantity": int(qty),
                    "buyer_agent_id": "BINANCE_BUYER",
                    "seller_agent_id": "BINANCE_SELLER",
                    "aggressor_side": "SELL" if maker_is_buyer else "BUY",
                }
            )
            self._last_update_ts = float(time.time() - self._start_ts)
            self._last_update_wall_time = time.time()

    def _record_event(self, event_type: str, message: str, severity: str) -> None:
        self._recent_events.append(
            {
                "ts": float(time.time() - self._start_ts),
                "type": event_type,
                "severity": severity,
                "message": message,
                "metadata": {},
            }
        )

    @staticmethod
    def provider_name() -> str:
        return "binance"
